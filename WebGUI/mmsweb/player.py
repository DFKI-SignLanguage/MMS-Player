"""Invocation of the MMS-Player (main.py inside Blender) and of the helper Blender scripts."""

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Dict, List, Optional

from .jobs import Job, run_process, error_summary

BLENDER_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "blender_scripts"
PROGRESS_HOOK = BLENDER_SCRIPTS_DIR / "progress_hook.py"
GLOSS_DURATIONS_SCRIPT = BLENDER_SCRIPTS_DIR / "gloss_durations.py"

MARKER = "@@MMSWEB "

# Fractions of the overall progress assigned to each phase of a render.
_P_STARTUP = 0.03
_P_BUILD_END = 0.30
_P_RENDER_END = 0.98


class RenderProgressTracker:
    """Interprets the output of the MMS-Player to update the job phase and progress."""

    def __init__(self, job: Job, expected_gloss_loads: int):
        self.job = job
        self.expected_loads = max(1, expected_gloss_loads)
        self.loads = 0
        self.rendering = False

    def feed(self, line: str) -> None:
        job = self.job
        if line.startswith(MARKER + "frame "):
            cur, start, end = (int(x) for x in line[len(MARKER) + 6:].split()[:3])
            total = max(1, end - start + 1)
            done = min(total, max(0, cur - start))
            self.rendering = True
            job.set_phase(f"Rendering video: frame {cur - start + 1} of {total}",
                          _P_BUILD_END + (_P_RENDER_END - _P_BUILD_END) * done / total)
        elif "Realizing MMS from file" in line:
            job.set_phase("Building the animation", _P_STARTUP)
        elif "Loading GLOSS animation data" in line:
            self.loads += 1
            frac = min(1.0, self.loads / self.expected_loads)
            job.set_phase(f"Loading signs ({min(self.loads, self.expected_loads)}/{self.expected_loads})",
                          _P_STARTUP + (_P_BUILD_END - _P_STARTUP) * 0.6 * frac)
        elif "Final animation realized" in line:
            job.set_phase("Applying inflections and preparing the scene", _P_BUILD_END - 0.02)
        elif line.startswith("Rendering done."):
            job.set_phase("Finishing", _P_RENDER_END)
        elif not self.rendering and ("inflection" in line.lower()) and job.progress is not None:
            # Slowly advance during the inflection stage, which has no explicit step count.
            job.progress = min(_P_BUILD_END - 0.03, job.progress + 0.002)


class PlayerRunner:

    def __init__(self, blender_exe: Path, player_dir: Path, dictionary_dir: Path):
        self.blender_exe = blender_exe
        self.player_dir = player_dir
        self.dictionary_dir = dictionary_dir
        self.main_py = player_dir / "main.py"

    def render_mp4(self, job: Job, mms_path: Path, mp4_path: Path, use_relative_time: bool,
                   render_size_pct: int, expected_gloss_loads: int,
                   target_fps: Optional[int] = None, gloss_panel: bool = False) -> None:

        args = [
            str(self.blender_exe),
            "--background",
            "--python-exit-code", "1",
            "--python", str(PROGRESS_HOOK),
            "--python", str(self.main_py),
            "--",
            "--source-mms-file", str(mms_path),
            "--dictionary-dir", str(self.dictionary_dir),
            "--export-mp4", str(mp4_path),
            "--render-size-pct", str(int(render_size_pct)),
            "--log-to-console",
        ]
        if use_relative_time:
            args.append("--use-relative-time")
        if target_fps:
            args.extend(["--target-fps", str(int(target_fps))])
        if gloss_panel:
            args.append("--gloss-panel")

        job.set_phase("Starting Blender", 0.0)
        tracker = RenderProgressTracker(job, expected_gloss_loads)
        rc = run_process(job, args, cwd=self.player_dir, on_line=tracker.feed)

        if rc != 0:
            raise RuntimeError(error_summary(job, f"The MMS-Player exited with code {rc}."))
        if not mp4_path.exists():
            raise RuntimeError(error_summary(job, "The MMS-Player did not produce the video."))

    def gloss_durations(self, job: Job, items: List[dict], on_result: Callable[[dict], None]) -> None:
        """items: list of {id, name, path}. Calls on_result({id, secs} | {id, error}) for each item."""

        def feed(line: str) -> None:
            if line.startswith(MARKER + "duration "):
                on_result(json.loads(line[len(MARKER) + 9:]))
            elif line.startswith(MARKER + "progress "):
                done, total = (int(x) for x in line[len(MARKER) + 9:].split()[:2])
                job.set_phase(f"Reading sign durations ({done}/{total})", done / max(1, total))

        with TemporaryDirectory(prefix="mmsweb-") as tmp:
            items_path = Path(tmp) / "items.json"
            items_path.write_text(json.dumps(items))
            args = [str(self.blender_exe), "--background", "--factory-startup",
                    "--python", str(GLOSS_DURATIONS_SCRIPT), "--", str(items_path)]
            job.set_phase("Reading sign durations", 0.0)
            rc = run_process(job, args, cwd=self.player_dir, on_line=feed)
        if rc != 0:
            raise RuntimeError(error_summary(job, f"Blender exited with code {rc}."))


def count_gloss_loads(rows: List[Dict[str, str]], hold_keyword: str) -> int:
    """Estimates how many gloss animations the player will load, for progress reporting."""
    n = 0
    for row in rows:
        for col in ("maingloss", "domarm", "ndomarm"):
            v = (row.get(col) or "").strip()
            if v and v != hold_keyword:
                n += 1
    return n


_SAFE_RE = re.compile(r"[^A-Za-z0-9._+-]+")


def safe_file_stem(text: str) -> str:
    return _SAFE_RE.sub("_", text).strip("._") or "gloss"
