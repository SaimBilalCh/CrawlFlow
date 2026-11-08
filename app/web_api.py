"""Local FastAPI bridge for operating the CrawlFlow collector from the web app."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PKG_DIR = Path(__file__).resolve().parent      # app/
ROOT = PKG_DIR.parent                          # CrawlFlow-bot/
# Plain (non-package) imports below need the app/ dir on sys.path
sys.path.insert(0, str(PKG_DIR))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

from config import CONFIG  # noqa: E402
from search_queries import FAKE_CATEGORIES, REAL_CATEGORIES  # noqa: E402

LOG_PATH = ROOT / "logs" / "collection.log"
PROGRESS_PATH = ROOT / "logs" / "progress.json"
SETUP_PATH = ROOT / "logs" / "setup.json"
ENV_PATH = ROOT / ".env"
WEB_DIR = ROOT / "web"
MAX_LINKS_PER_SUBMIT = 200
MAX_TXT_UPLOAD_BYTES = 1024 * 1024
STATE_LOCK = threading.Lock()
RUNNING = False
ACTIVE_RUN: dict | None = None
DRIVE_AUTH = {"state": "idle", "error": None}

app = FastAPI(title="CrawlFlow Local Collector API", version="1.0.0")

# Persist collector/log_engine messages (uvicorn doesn't configure the root logger)
logs_dir = ROOT / "logs"
logs_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(logs_dir / "collection.log", encoding="utf-8")],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def local_only(request, call_next):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return JSONResponse({"detail": "The collector API only accepts local connections."}, status_code=403)
    return await call_next(request)


class RunRequest(BaseModel):
    label: Literal["real", "fake"]
    category: str
    max_videos: int = Field(default=25, ge=1, le=100)


def read_progress() -> dict:
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        return {
            "real": data.get("real", []),
            "fake": data.get("fake", []),
            "processed": data.get("processed", []),
        }
    except (OSError, json.JSONDecodeError):
        return {"real": [], "fake": [], "processed": []}


def read_logs(limit: int = 120) -> list[str]:
    try:
        with LOG_PATH.open("r", encoding="utf-8", errors="replace") as log_file:
            return list(deque((line.rstrip() for line in log_file), maxlen=limit))
    except OSError:
        return []


def runtime_status() -> dict:
    credentials = ROOT / "credentials" / "credentials.json"
    token = ROOT / "credentials" / "token.json"
    drive_folder = CONFIG.get("DRIVE_FOLDER_ID")
    cookies = ROOT / "cookies"
    platforms = {
        name: {
            "enabled": bool(settings.get("enabled")),
            "cookie_configured": (cookies / f"{name}_cookies.txt").is_file(),
        }
        for name, settings in CONFIG.get("PLATFORMS", {}).items()
    }
    return {
        "drive_folder_configured": bool(drive_folder),
        "drive_credentials_configured": credentials.is_file(),
        "drive_authenticated": token.is_file(),
        "drive_authorization_in_progress": DRIVE_AUTH.get("state") == "pending",
        "platforms": platforms,
    }


@app.get("/api/status")
def get_status() -> dict:
    with STATE_LOCK:
        active = dict(ACTIVE_RUN) if ACTIVE_RUN else None
        running = RUNNING
    progress = read_progress()
    return {
        "running": running,
        "active_run": active,
        "progress": {
            "real": len(progress["real"]),
            "fake": len(progress["fake"]),
            "processed": list(reversed(progress["processed"][-20:])),
        },
        "targets": {"real": CONFIG["TARGET_REAL"], "fake": CONFIG["TARGET_FAKE"]},
        "settings": runtime_status(),
        "logs": read_logs(),
    }


@app.get("/api/categories")
def get_categories() -> dict:
    return {
        "real": list(REAL_CATEGORIES.keys()),
        "fake": list(FAKE_CATEGORIES.keys()),
    }


def run_collector(request: RunRequest) -> None:
    global RUNNING, ACTIVE_RUN
    try:
        from main import DeepfakeCollector

        collector = DeepfakeCollector()
        collector.config["BATCH_SIZE"] = request.max_videos
        logging.info(
            "Dashboard started %s/%s (up to %s search results)",
            request.label,
            request.category,
            request.max_videos,
        )
        collector.process_category(request.category, request.label)
        logging.info("Dashboard collection finished for %s/%s", request.label, request.category)
    except Exception:
        logging.exception("Dashboard collector failed")
    finally:
        with STATE_LOCK:
            RUNNING = False
            ACTIVE_RUN = None


@app.post("/api/runs")
def start_run(request: RunRequest) -> dict:
    global RUNNING, ACTIVE_RUN
    categories = REAL_CATEGORIES if request.label == "real" else FAKE_CATEGORIES
    if request.category not in categories:
        raise HTTPException(status_code=400, detail="Choose a category from the list.")

    with STATE_LOCK:
        if RUNNING:
            raise HTTPException(status_code=409, detail="A collection run is already active.")
        if (ROOT / "credentials" / "token.json").is_file() is False:
            missing = []
            if not CONFIG.get("DRIVE_FOLDER_ID"):
                missing.append("DRIVE_FOLDER_ID in .env")
            if not (ROOT / "credentials" / "credentials.json").is_file():
                missing.append("credentials/credentials.json")
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail="Complete Google Drive setup before collecting: " + ", ".join(missing),
                )
        RUNNING = True
        ACTIVE_RUN = {
            "label": request.label,
            "category": request.category,
            "max_videos": request.max_videos,
        }

    threading.Thread(target=run_collector, args=(request,), daemon=True).start()
    return {"accepted": True, "active_run": ACTIVE_RUN}


# ===================== Link processing =====================


def read_jobs():
    from link_processor import processor

    return processor


@app.get("/api/queue/status")
def queue_status() -> dict:
    proc = read_jobs()
    return {"stats": proc.stats(), "jobs": proc.list_jobs()}


class JobRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=MAX_LINKS_PER_SUBMIT)
    label: Literal["real", "fake"]
    category: str


@app.post("/api/jobs")
def create_jobs(request: JobRequest) -> dict:
    proc = read_jobs()
    categories = REAL_CATEGORIES if request.label == "real" else FAKE_CATEGORIES
    if request.category not in categories:
        raise HTTPException(status_code=400, detail="Choose a category from the list.")
    accepting = bool((ROOT / "credentials" / "token.json").is_file() and CONFIG.get("DRIVE_FOLDER_ID"))
    if not accepting:
        raise HTTPException(status_code=400, detail="Complete first-time setup before uploading links.")
    accepted, rejected = proc.submit([u.strip() for u in request.urls if u.strip()], request.label, request.category)
    return {"accepted": accepted, "rejected": rejected}


@app.post("/api/jobs/upload")
async def upload_links_file(label: Literal["real", "fake"], category: str, file: UploadFile = File(...)) -> dict:
    proc = read_jobs()
    categories = REAL_CATEGORIES if label == "real" else FAKE_CATEGORIES
    if category not in categories:
        raise HTTPException(status_code=400, detail="Choose a category from the list.")
    if (file.filename or "").lower().endswith(".txt") is False:
        raise HTTPException(status_code=400, detail="Only .txt files are accepted.")
    data = await file.read()
    if len(data) > MAX_TXT_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 1 MB).")
    urls = [line.strip() for line in data.decode("utf-8-sig", errors="replace").splitlines() if line.strip() and not line.strip().startswith("#")]
    urls = urls[:MAX_LINKS_PER_SUBMIT]
    accepted, rejected = proc.submit(urls, label, category)
    return {"accepted": accepted, "rejected": rejected}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict:
    if not read_jobs().retry(job_id):
        raise HTTPException(status_code=404, detail="Job not found or not retryable.")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    if not read_jobs().cancel(job_id):
        raise HTTPException(status_code=404, detail="Job not found or not cancellable.")
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard() -> dict:
    proc = read_jobs()
    stats = proc.stats()
    drive_info = {"connected": False, "videos": 0, "folders": 0, "used_gb": None, "total_gb": None}
    try:
        uploader = proc.get_uploader()
        all_items = collect_drive_items(uploader)
        drive_info["connected"] = True
        drive_info["videos"] = sum(1 for i in all_items if i["kind"] == "file" and i["name"].lower().endswith(".mp4"))
        drive_info["folders"] = sum(1 for i in all_items if i["kind"] == "folder")
        about = uploader.service.about().get(fields="storageQuota").execute()
        drive_info["used_gb"] = round(int(about.get("storageQuota", {}).get("usage", 0)) / 1024**3, 2)
        drive_info["total_gb"] = round(int(about.get("storageQuota", {}).get("limit", 0)) / 1024**3, 2)
    except Exception as error:
        drive_info["error"] = str(error)[:200]
    recent = [j for j in proc.list_jobs() if j["status"] != "pending"][:8]
    return {"stats": stats, "drive": drive_info, "recent": recent, "settings": runtime_status()}


# ===================== Recent Drive uploads =====================


def collect_drive_items(uploader) -> list[dict]:
    folder_map = {
        "Root": uploader.folder_id,
        "Real_Videos": uploader.real_folder_id,
        "Fake_Videos": uploader.fake_folder_id,
        "Metadata": uploader.metadata_folder_id,
    }
    items = []
    for folder_name, folder_id in folder_map.items():
        if not folder_id:
            continue
        query = f"'{folder_id}' in parents and trashed=false"
        results = uploader.service.files().list(
            q=query, orderBy="modifiedTime desc", pageSize=100,
            fields="files(id, name, mimeType, size, modifiedTime, webViewLink, description)",
        ).execute()
        for f in results.get("files", []):
            is_folder = f.get("mimeType") == "application/vnd.google-apps.folder"
            item = {
                "id": f["id"],
                "name": f["name"],
                "kind": "folder" if is_folder else "file",
                "size_bytes": int(f["size"]) if f.get("size") else None,
                "modified_time": f.get("modifiedTime"),
                "drive_link": f.get("webViewLink"),
                "folder": folder_name if not is_folder else None,
            }
            if f.get("description"):
                try:
                    desc = json.loads(f["description"])
                    item["source_url"] = desc.get("original_url")
                    item["label"] = desc.get("label")
                    item["category"] = desc.get("category")
                except (ValueError, TypeError):
                    pass
            items.append(item)
    items.sort(key=lambda x: x["modified_time"] or "", reverse=True)
    return items


@app.get("/api/drive/uploads")
def drive_uploads(search: str | None = None) -> dict:
    try:
        uploader = read_jobs().get_uploader()
        if uploader is None:
            raise RuntimeError("Google Drive is not configured. Complete setup in Settings.")
        items = collect_drive_items(uploader)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Could not list Drive uploads: {error}")
    if search:
        needle = search.lower()
        items = [i for i in items if needle in i["name"].lower() or needle in (i.get("source_url") or "").lower()]
    return {"items": items, "storage": {"videos": sum(1 for i in items if i["kind"] == "file" and i["name"].lower().endswith(".mp4"))}}


@app.get("/api/drive/test")
def drive_test() -> dict:
    try:
        uploader = read_jobs().reload_uploader()
        if uploader is None:
            raise RuntimeError("Drive uploader could not start; check DRIVE_FOLDER_ID and credentials.")
        files = uploader.service.files().list(q=f"'{uploader.folder_id}' in parents and trashed=false", pageSize=1, fields="files(id)").execute()
        return {"ok": True, "detail": f"Connected to Drive folder {uploader.folder_id} ({len(files.get('files', []))} items visible)."}
    except Exception as error:
        return {"ok": False, "detail": str(error)[:300]}


# ===================== Drive OAuth =====================


def _oauth_worker():
    DRIVE_AUTH["state"] = "pending"
    DRIVE_AUTH["error"] = None
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(ROOT / "credentials" / "credentials.json"), ["https://www.googleapis.com/auth/drive.file"]
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        (ROOT / "credentials" / "token.json").write_text(creds.to_json(), encoding="utf-8")
        DRIVE_AUTH["state"] = "done"
        read_jobs().reload_uploader()
    except Exception as error:
        DRIVE_AUTH["state"] = "failed"
        DRIVE_AUTH["error"] = str(error)[:300]


@app.get("/api/drive/auth")
def drive_auth_status() -> dict:
    return dict(DRIVE_AUTH)


@app.post("/api/drive/auth")
def drive_auth_start() -> dict:
    if DRIVE_AUTH["state"] == "pending":
        raise HTTPException(status_code=409, detail="A Google sign-in window is already open.")
    creds = ROOT / "credentials" / "credentials.json"
    if not creds.is_file():
        raise HTTPException(status_code=400, detail="credentials/credentials.json is missing. Add it first.")
    threading.Thread(target=_oauth_worker, daemon=True).start()
    return {"accepted": True}


# ===================== Settings & first-run setup =====================


EDITABLE_CONFIG_KEYS = ["DRIVE_FOLDER_ID", "CRAWLFLOW_BATCH_SIZE", "CRAWLFLOW_TARGET_REAL", "CRAWLFLOW_TARGET_FAKE"]


def read_env_file() -> list[str]:
    try:
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def write_env_file(lines: list[str]):
    temp = ENV_PATH.with_suffix(".tmp")
    temp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    temp.replace(ENV_PATH)


@app.get("/api/settings")
def get_settings() -> dict:
    env = {}
    for line in read_env_file():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"')
    return {
        "drive": {
            "folder_id": CONFIG.get("DRIVE_FOLDER_ID") or "",
            "credentials_present": (ROOT / "credentials" / "credentials.json").is_file(),
            "token_present": (ROOT / "credentials" / "token.json").is_file(),
            "auth_state": DRIVE_AUTH["state"],
            "auth_error": DRIVE_AUTH["error"],
        },
        "crawler": {
            "batch_size": CONFIG["BATCH_SIZE"],
            "target_real": CONFIG["TARGET_REAL"],
            "target_fake": CONFIG["TARGET_FAKE"],
        },
        "platforms": CONFIG["PLATFORMS"],
        "env_keys_present": {key: key in env for key in EDITABLE_CONFIG_KEYS},
    }


class SettingsRequest(BaseModel):
    folder_id: str | None = Field(default=None, max_length=120)
    batch_size: int | None = Field(default=None, ge=1, le=100)
    target_real: int | None = Field(default=None, ge=1, le=100000)
    target_fake: int | None = Field(default=None, ge=1, le=100000)


@app.post("/api/settings")
def save_settings(request: SettingsRequest) -> dict:
    updates: dict[str, str] = {}
    if request.folder_id is not None:
        request.folder_id = request.folder_id.strip()
        if request.folder_id and (len(request.folder_id) < 10 or any(c in request.folder_id for c in " /?#")):
            raise HTTPException(status_code=400, detail="That does not look like a Google Drive folder ID.")
        updates["DRIVE_FOLDER_ID"] = request.folder_id
        CONFIG["DRIVE_FOLDER_ID"] = request.folder_id or None
    if request.batch_size is not None:
        updates["CRAWLFLOW_BATCH_SIZE"] = str(request.batch_size)
        CONFIG["BATCH_SIZE"] = request.batch_size
    if request.target_real is not None:
        updates["CRAWLFLOW_TARGET_REAL"] = str(request.target_real)
        CONFIG["TARGET_REAL"] = request.target_real
    if request.target_fake is not None:
        updates["CRAWLFLOW_TARGET_FAKE"] = str(request.target_fake)
        CONFIG["TARGET_FAKE"] = request.target_fake

    if updates:
        lines = read_env_file()
        seen: set[str] = set()
        new_lines = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else None
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                new_lines.append(line)
        for key, value in updates.items():
            if key not in seen:
                new_lines.append(f"{key}={value}")
        write_env_file(new_lines)
        if "DRIVE_FOLDER_ID" in updates:
            # never leave a stale uploader bound to the old folder
            read_jobs().reload_uploader()
    return {"ok": True, "settings": get_settings()}


@app.get("/api/setup/state")
def setup_state() -> dict:
    complete = SETUP_PATH.is_file()
    token_ok = (ROOT / "credentials" / "token.json").is_file()
    folder_ok = bool(CONFIG.get("DRIVE_FOLDER_ID"))
    return {
        "complete": complete,
        "credentials_present": (ROOT / "credentials" / "credentials.json").is_file(),
        "token_present": token_ok,
        "folder_id_set": folder_ok,
        "auth_state": DRIVE_AUTH["state"],
        "auth_error": DRIVE_AUTH["error"],
    }


@app.post("/api/setup/complete")
def setup_complete() -> dict:
    state = setup_state()
    if not (state["token_present"] and state["folder_id_set"]):
        raise HTTPException(status_code=400, detail="Authorize Google and set the Drive folder ID before finishing setup.")
    test = drive_test()
    if not test["ok"]:
        raise HTTPException(status_code=400, detail=test["detail"])
    SETUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETUP_PATH.write_text(json.dumps({"completed_at": datetime.now().isoformat()}), encoding="utf-8")
    return {"ok": True}


@app.post("/api/setup/reset")
def setup_reset() -> dict:
    if SETUP_PATH.is_file():
        SETUP_PATH.unlink()
    return {"ok": True}


@app.post("/api/setup/credentials")
async def setup_credentials(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="credentials.json must be a .json file.")
    data = await file.read()
    if len(data) > 256 * 1024:
        raise HTTPException(status_code=400, detail="File too large for an OAuth client file.")
    try:
        parsed = json.loads(data)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not valid JSON.")
    if not isinstance(parsed, dict) or not any(key in parsed for key in ("installed", "web")):
        raise HTTPException(status_code=400, detail='This does not look like a Google OAuth client file (missing "installed"/"web" section).')
    (ROOT / "credentials").mkdir(exist_ok=True)
    (ROOT / "credentials" / "credentials.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return {"ok": True, "credentials_present": True}


# ===================== Static frontend =====================

if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
