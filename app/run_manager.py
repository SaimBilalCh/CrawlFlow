# run_manager.py - Timed auto-collector sessions for the web panel.
# Wraps DeepfakeCollector: one thread, a deadline, ordered category cycling,
# an optional stop flag, and session state persisted to logs/collector_session.json.

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import CONFIG
from search_queries import REAL_CATEGORIES, FAKE_CATEGORIES

logger = logging.getLogger(__name__)

PKG_DIR = Path(__file__).resolve().parent
ROOT = PKG_DIR.parent
SESSION_PATH = ROOT / "logs" / "collector_session.json"
PROGRESS_PATH = ROOT / "logs" / "progress.json"

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"
STATUS_STOPPED = "stopped"
STATUS_INTERRUPTED = "interrupted"

# Pause between categories, checked in slices so Stop reacts quickly.
PAUSE_S = 45
PAUSE_SLICE_S = 2


class CollectorSession:
    def __init__(self):
        self._lock = threading.RLock()  # reentrant: start() calls status()/is_running() while held
        self._stop = threading.Event()
        self._current: dict | None = None  # {"label","category"} while a category runs
        self._session: dict | None = None
        self._last: str | None = None      # previous label, for real/fake alternation

        existing = self._load()
        if existing:
            if existing.get("status") == STATUS_RUNNING:
                # process died mid-session; not a live session anymore
                existing["status"] = STATUS_INTERRUPTED
                existing["reason"] = "Interrupted by application restart."
                self._save(existing)
            self._session = existing  # keep the last session visible on the panel

    # ---------- persistence ----------

    @staticmethod
    def _load() -> dict | None:
        try:
            return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _save(data: dict):
        temp = SESSION_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp.replace(SESSION_PATH)

    @staticmethod
    def _progress_counts() -> dict:
        try:
            data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
            return {"real": len(data.get("real", [])), "fake": len(data.get("fake", []))}
        except (OSError, json.JSONDecodeError):
            return {"real": 0, "fake": 0}

    # ---------- API ----------

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._session and self._session.get("status") == STATUS_RUNNING)

    def start(self) -> dict | None:
        with self._lock:
            if self.is_running():
                return None
            self._stop.clear()
            minutes = int(CONFIG.get("RUN_MINUTES") or 60)
            started = datetime.now()
            self._session = {
                "status": STATUS_RUNNING,
                "started_at": started.isoformat(),
                "deadline_at": (started + timedelta(minutes=minutes)).isoformat(),
                "duration_minutes": minutes,
                "baseline": self._progress_counts(),
                "current": None,
                "reason": None,
                "error": None,
            }
            self._save(self._session)
        threading.Thread(target=self._worker, daemon=True, name="crawlflow-collector-session").start()
        return self.status()

    def stop(self) -> bool:
        if not self.is_running():
            return False
        self._stop.set()
        return True

    def status(self) -> dict:
        with self._lock:
            data = dict(self._session) if self._session else {"status": STATUS_IDLE}
        if data.get("status") == STATUS_RUNNING:
            try:
                data["remaining_s"] = max(0, int(
                    (datetime.fromisoformat(data["deadline_at"]) - datetime.now()).total_seconds()))
            except (KeyError, ValueError):
                data["remaining_s"] = None
            data["current"] = self._current
        totals = self._progress_counts()
        data["totals"] = totals
        base = data.get("baseline") or {"real": 0, "fake": 0}
        data["gained"] = {k: max(0, totals.get(k, 0) - base.get(k, 0)) for k in ("real", "fake")}
        return data

    # ---------- worker ----------

    def _worker(self):
        try:
            from main import DeepfakeCollector

            collector = DeepfakeCollector()
        except Exception as error:
            with self._lock:
                self._session.update(
                    status=STATUS_FINISHED, reason="Could not start the collector engine.", error=str(error)[:300])
                self._save(self._session)
            logger.exception("Collector session failed to start")
            return
        try:
            reason = self._run_loop(collector)
            interrupted = self._stop.is_set()
            with self._lock:
                self._session.update(
                    status=STATUS_STOPPED if interrupted else STATUS_FINISHED,
                    reason=reason or ("Stopped by user." if interrupted else "Session time is over."),
                    current=None,
                )
                self._current = None
                self._save(self._session)
        except Exception as error:
            logger.exception("Collector session crashed")
            with self._lock:
                self._session.update(status=STATUS_FINISHED, reason="Collector crashed.", error=str(error)[:300])
                self._current = None
                self._save(self._session)

    def _run_loop(self, collector) -> str | None:
        """Cycle real/fake categories in order until deadline, targets, or stop."""
        deadline = datetime.fromisoformat(self.status()["deadline_at"])
        real_cats = list(REAL_CATEGORIES.keys())
        fake_cats = list(FAKE_CATEGORIES.keys())
        order = {"real": 0, "fake": 0}

        while not self._stop.is_set():
            if datetime.now() >= deadline:
                return "Session time is over."

            # alternate real/fake; fall back to whichever label still has headroom
            if collector.real_count < CONFIG["TARGET_REAL"] and (
                not collector.fake_count < CONFIG["TARGET_FAKE"] or self._last != "real"
            ):
                label = "real"
            elif collector.fake_count < CONFIG["TARGET_FAKE"]:
                label = "fake"
            elif collector.real_count < CONFIG["TARGET_REAL"]:
                label = "real"
            else:
                return "All collection targets reached."

            cats = real_cats if label == "real" else fake_cats
            if not cats:
                return f"No categories configured for {label}."
            category = cats[order[label] % len(cats)]
            order[label] += 1
            self._last = label

            logger.info("SESSION: %s/%s", label, category)
            self._current = {"label": label, "category": category}
            collector.process_category(category, label, should_stop=self._stop.is_set)
            self._current = None

            if self._stop.is_set():
                return None
            # stop/deadline-aware pause between categories
            wake = min(datetime.now() + timedelta(seconds=PAUSE_S), deadline)
            while not self._stop.is_set() and datetime.now() < wake:
                time.sleep(PAUSE_SLICE_S)
        return None


session = CollectorSession()
