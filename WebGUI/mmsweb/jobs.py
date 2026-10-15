"""Background jobs (Blender processes) with progress reporting."""

import os
import re
import subprocess
import threading
import time
import traceback
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional

MAX_KEPT_JOBS = 300


class JobCancelled(Exception):
    pass


class Job:

    def __init__(self, kind: str, title: str, key: Optional[str] = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.key = key
        self.status = "queued"  # queued | running | done | error | cancelled
        self.phase = "Waiting in queue"
        self.progress: Optional[float] = None  # 0..1, None when indeterminate
        self.error: Optional[str] = None
        self.result: dict = {}
        self.log: deque = deque(maxlen=500)
        self.created = time.time()
        self.started: Optional[float] = None
        self.finished: Optional[float] = None
        self.cancel_requested = False
        self._proc: Optional[subprocess.Popen] = None

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "error", "cancelled")

    def set_phase(self, phase: str, progress: Optional[float] = None) -> None:
        self.phase = phase
        self.progress = progress

    def to_dict(self, with_log: bool = False) -> dict:
        now = time.time()
        d = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "error": self.error,
            "result": self.result,
            "elapsed": round(((self.finished or now) - self.started), 1) if self.started else 0.0,
        }
        if with_log:
            d["log"] = list(self.log)
        return d


class JobQueue:
    """A pool of workers executing jobs in FIFO order.
    Jobs with the same key are de-duplicated while they are not finished."""

    def __init__(self, name: str, workers: int):
        self.name = name
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"mmsweb-{name}")
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._by_key: Dict[str, Job] = {}

    def submit(self, job: Job, fn: Callable[[Job], None]) -> Job:
        with self._lock:
            if job.key is not None:
                existing = self._by_key.get(job.key)
                if existing is not None and not existing.is_finished:
                    return existing
                self._by_key[job.key] = job
            self._jobs[job.id] = job
            self._prune()
        self._executor.submit(self._run, job, fn)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None or job.is_finished:
            return job
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
            job.phase = "Cancelled"
            job.finished = time.time()
        elif job._proc is not None and job._proc.poll() is None:
            job._proc.terminate()
        return job

    def _run(self, job: Job, fn: Callable[[Job], None]) -> None:
        if job.cancel_requested:
            return
        job.status = "running"
        job.started = time.time()
        job.set_phase("Starting")
        try:
            fn(job)
            if job.cancel_requested:
                raise JobCancelled()
            job.status = "done"
            job.set_phase("Done", 1.0)
        except JobCancelled:
            job.status = "cancelled"
            job.set_phase("Cancelled")
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            job.phase = "Failed"
            job.log.append(traceback.format_exc())
        finally:
            job.finished = time.time()

    def _prune(self) -> None:
        if len(self._jobs) <= MAX_KEPT_JOBS:
            return
        finished = sorted((j for j in self._jobs.values() if j.is_finished), key=lambda j: j.created)
        for j in finished[: len(self._jobs) - MAX_KEPT_JOBS]:
            del self._jobs[j.id]
            if j.key is not None and self._by_key.get(j.key) is j:
                del self._by_key[j.key]


def run_process(job: Job, args: List[str], cwd: Path, on_line: Callable[[str], None]) -> int:
    """Runs a process, feeding each output line (stdout and stderr) to the job log and to on_line."""

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    job.log.append("$ " + " ".join(f'"{a}"' if " " in a else a for a in args))
    proc = subprocess.Popen(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, bufsize=1, errors="replace", env=env)
    job._proc = proc
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            job.log.append(line)
            try:
                on_line(line)
            except Exception:
                pass
            if job.cancel_requested and proc.poll() is None:
                proc.terminate()
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
        job._proc = None
        if job.cancel_requested:
            raise JobCancelled()


_EXCEPTION_RE = re.compile(r"^[\w.]*(Error|Exception)(: .*)?$")


def error_summary(job: Job, fallback: str) -> str:
    """Extracts a meaningful error message (the last Python exception) from the end of the job log."""
    lines = [l.strip() for l in job.log if l.strip()][-80:]
    for line in reversed(lines):
        if _EXCEPTION_RE.match(line) and not line.startswith("Error: script failed"):
            return line
    return fallback
