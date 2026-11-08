# link_processor.py - Per-link processing engine for the CrawlFlow web panel.
# Extracted from bulk_upload_gui.py so the web UI and legacy GUI share one engine.

import hashlib
import json
import logging
import os
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from config import CONFIG
from drive_uploader import DriveUploader

logger = logging.getLogger(__name__)

JOBS_PATH = Path(__file__).resolve().parent.parent / "logs" / "jobs.json"

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def is_valid_url(url: str) -> bool:
    try:
        parsed_url = urlparse(url)
    except ValueError:
        return False
    return parsed_url.scheme in ("http", "https") and bool(parsed_url.netloc)


def detect_platform(url: str) -> str:
    lowered = url.lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "tiktok.com" in lowered:
        return "tiktok"
    if "facebook.com" in lowered or "fb.com" in lowered:
        return "facebook"
    return "other"


class LinkProcessor:
    """Sequential job queue: one link at a time, persisted to logs/jobs.json."""

    def __init__(self):
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._jobs: list[dict] = []
        self._uploader = None
        self._load_and_recover()
        threading.Thread(target=self._worker, daemon=True, name="crawllow-link-worker").start()

    # ---------- persistence ----------

    def _load_and_recover(self):
        if JOBS_PATH.exists():
            try:
                self._jobs = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._jobs = []
        for job in self._jobs:
            if job.get("status") == STATUS_PROCESSING:
                # interrupted by a previous shutdown; retryable through the UI
                job["status"] = STATUS_FAILED
                job["error"] = "Interrupted by application restart."
            elif job.get("status") == STATUS_PENDING:
                self._queue.put(job["id"])
        if self._jobs:
            self._save()

    def _save(self):
        temp = JOBS_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")
        temp.replace(JOBS_PATH)

    # ---------- uploader lifecycle ----------

    def reload_uploader(self):
        try:
            self._uploader = DriveUploader(CONFIG)
        except Exception as error:
            logger.warning("Drive uploader unavailable: %s", error)
            self._uploader = None
        return self._uploader

    def get_uploader(self):
        if self._uploader is None:
            return self.reload_uploader()
        return self._uploader

    # ---------- API used by web_api.py ----------

    def submit(self, urls: list[str], label: str, category: str) -> tuple[list[dict], list[dict]]:
        """Create pending jobs. Returns (accepted, rejected) with reasons."""
        accepted, rejected = [], []
        active_urls = {
            job["url"]
            for job in self._jobs
            if job["status"] in (STATUS_PENDING, STATUS_PROCESSING)
        }
        seen_in_batch = set()
        with self._lock:
            for url in urls:
                if not is_valid_url(url):
                    rejected.append({"url": url, "reason": "Not a valid http(s) URL."})
                    continue
                if url in seen_in_batch or url in active_urls:
                    rejected.append({"url": url, "reason": "Duplicate of a link already queued or processing."})
                    continue
                seen_in_batch.add(url)
                job = {
                    "id": uuid.uuid4().hex[:12],
                    "url": url,
                    "platform": detect_platform(url),
                    "label": label,
                    "category": category,
                    "status": STATUS_PENDING,
                    "error": None,
                    "queued_at": datetime.now().isoformat(),
                    "started_at": None,
                    "finished_at": None,
                    "duration_s": None,
                    "drive_file_id": None,
                    "drive_name": None,
                    "drive_link": None,
                }
                self._jobs.append(job)
                self._queue.put(job["id"])
                accepted.append({"url": url, "id": job["id"]})
            self._save()
        return accepted, rejected

    def retry(self, job_id: str) -> bool:
        with self._lock:
            job = next((j for j in self._jobs if j["id"] == job_id), None)
            if not job or job["status"] != STATUS_FAILED:
                return False
            job.update(status=STATUS_PENDING, error=None, finished_at=None)
            self._queue.put(job_id)
            self._save()
        return True

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = next((j for j in self._jobs if j["id"] == job_id), None)
            if not job or job["status"] != STATUS_PENDING:
                return False
            job["status"] = "cancelled"
            self._save()
        return True

    def list_jobs(self) -> list[dict]:
        return list(reversed(self._jobs))  # newest first

    def stats(self) -> dict:
        counts = {STATUS_PENDING: 0, STATUS_PROCESSING: 0, STATUS_COMPLETED: 0, STATUS_FAILED: 0}
        for job in self._jobs:
            if job["status"] in counts:
                counts[job["status"]] += 1
        return counts

    # ---------- worker ----------

    def _worker(self):
        while True:
            job_id = self._queue.get()
            with self._lock:
                job = next((j for j in self._jobs if j["id"] == job_id), None)
                if not job or job["status"] != STATUS_PENDING:
                    continue
                job["status"] = STATUS_PROCESSING
                job["started_at"] = datetime.now().isoformat()
                self._save()
            try:
                self._process_job(job)
            except Exception as error:
                job["status"] = STATUS_FAILED
                job["error"] = f"Unexpected error: {error}"
                import traceback
                logger.error("Job %s crashed:\n%s", job.get("id"), traceback.format_exc())
            job["finished_at"] = datetime.now().isoformat()
            job["duration_s"] = round(
                (datetime.fromisoformat(job["finished_at"]) - datetime.fromisoformat(job["started_at"])).total_seconds(), 1
            )
            with self._lock:
                self._save()
            self._queue.task_done()

    # ---------- per-link engine (mirrors bulk_upload_gui.py) ----------

    def _download(self, url: str, platform: str) -> Path | None:
        ydl_opts = {
            "outtmpl": os.path.join(CONFIG["PATHS"]["download"], f"{platform}_%(id)s.%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "sleep_interval": 3,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "extractor_args": {"youtube": {"skip": ["dash", "hls"]}},
        }
        if platform in ("tiktok", "facebook"):
            cookie_file = Path(CONFIG["PATHS"]["cookies"]) / f"{platform}_cookies.txt"
            if cookie_file.exists():
                ydl_opts["cookiefile"] = str(cookie_file)

        # Route yt-dlp output through stdlib logging: the uvicorn console may
        # not be UTF-8 and yt-dlp doubles the encoding otherwise.
        class YdlLogger:
            def debug(self, msg):
                if msg.startswith("[debug]"):
                    logger.debug(msg[7:].strip())
                else:
                    logger.info(msg.strip())
            def warning(self, msg):
                logger.warning(msg.strip())
            def error(self, msg):
                logger.error(msg.strip())

        ydl_opts["logger"] = YdlLogger()
        ydl_opts["noprogress"] = True

        download_path = Path(CONFIG["PATHS"]["download"])
        download_path.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in download_path.glob(f"{platform}_*.mp4")}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        candidates = [p for p in download_path.glob(f"{platform}_*.mp4") if p.name not in before]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _process_job(self, job: dict):
        uploader = self.get_uploader()
        if uploader is None:
            job["status"] = STATUS_FAILED
            job["error"] = "Google Drive is not configured. Complete setup in Settings first."
            return

        try:
            video_path = self._download(job["url"], job["platform"])
        except yt_dlp.utils.DownloadError as error:
            job["status"] = STATUS_FAILED
            job["error"] = f"Download failed: {str(error)[:300]}"
            return
        if video_path is None or not video_path.exists():
            job["status"] = STATUS_FAILED
            job["error"] = "Download produced no video file."
            return
        job["drive_name"] = video_path.name

        video_hash = hashlib.md5(video_path.stem.encode()).hexdigest()[:16]
        try:
            from metadata_extractor import MetadataExtractor

            platform_meta = MetadataExtractor().extract_platform_metadata(job["url"])
            title = platform_meta.get("title", "unknown")
        except Exception:
            title = "unknown"

        metadata = {
            "label": job["label"],
            "category": job["category"],
            "sha256_hash": video_hash,
            "original_url": job["url"],
            "platform": job["platform"],
            "source_title": str(title)[:200],
            "duration": 10,
            "resolution": "unknown",
            "fps": 0,
            "download_timestamp": datetime.now().isoformat(),
        }

        result = uploader.upload_video(str(video_path), metadata)
        try:
            os.remove(video_path)
        except OSError:
            pass

        if not result:
            job["status"] = STATUS_FAILED
            job["error"] = "Google Drive upload failed after retries."
            return

        job.update(
            status=STATUS_COMPLETED,
            error=None,
            drive_file_id=result["video_id"],
            drive_name=result["video_name"],
            drive_link=f"https://drive.google.com/file/d/{result['video_id']}/view",
        )


processor = LinkProcessor()
