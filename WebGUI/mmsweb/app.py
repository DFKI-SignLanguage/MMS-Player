"""Flask application of the MMS-Player web GUI."""

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from . import __version__
from .dictionary import Dictionary, split_gloss_id
from .jobs import Job, JobQueue
from .mms_io import (MMS_SUFFIX, clean_rows, normalize_mms_name, parse_mms, read_mms_file,
                     serialize_mms, write_mms_file)
from .player import PlayerRunner, count_gloss_loads, safe_file_stem
from .schema import HOLD_KEYWORD, schema_for_client

WEBGUI_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ServerConfig:
    dictionary_dir: Path
    player_dir: Path
    project_dir: Path
    blender_exe: Path
    render_workers: int = 1
    preview_size_pct: int = 25
    default_render_size_pct: int = 50
    target_fps: int = 30
    font_size_px: float = 13


class DurationCache:
    """Original duration (seconds) of the dictionary glosses, persisted on disk."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.values: Dict[str, float] = {}
        self.errors: Dict[str, str] = {}
        self.pending: set = set()
        if path.exists():
            try:
                self.values = {k: float(v) for k, v in json.loads(path.read_text()).items()}
            except Exception:
                self.values = {}

    def store(self, gloss_id: str, secs: Optional[float], error: Optional[str] = None) -> None:
        with self.lock:
            if secs is not None:
                self.values[gloss_id] = secs
            else:
                self.errors[gloss_id] = error or "unknown error"

    def save(self) -> None:
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.values, indent=0, sort_keys=True))
            tmp.replace(self.path)


def create_app(cfg: ServerConfig) -> Flask:

    app = Flask(__name__, template_folder=str(WEBGUI_DIR / "templates"), static_folder=str(WEBGUI_DIR / "static"))
    app.json.sort_keys = False

    cache_dir = cfg.project_dir / ".mmsweb-cache"
    previews_dir = cache_dir / "previews"
    renders_dir = cfg.project_dir / "renders"
    examples_dir = cfg.player_dir / "MMS-examples"
    for d in (cfg.project_dir, cache_dir, previews_dir, renders_dir):
        d.mkdir(parents=True, exist_ok=True)

    dictionary = Dictionary(cfg.dictionary_dir)
    runner = PlayerRunner(cfg.blender_exe, cfg.player_dir, cfg.dictionary_dir)
    render_queue = JobQueue("render", cfg.render_workers)
    aux_queue = JobQueue("aux", 1)  # sign previews and durations: don't wait behind long renders
    durations = DurationCache(cache_dir / "durations.json")

    def find_job(job_id: str) -> Optional[Job]:
        return render_queue.get(job_id) or aux_queue.get(job_id)

    def preview_path(gloss_id: str) -> Path:
        cls, name = split_gloss_id(gloss_id)
        return previews_dir / safe_file_stem(cls) / (safe_file_stem(name) + ".mp4")

    def preview_url(gloss_id: str) -> str:
        p = preview_path(gloss_id)
        return f"/media/previews/{p.parent.name}/{p.name}?v={int(p.stat().st_mtime)}"

    def bad_request(msg: str, code: int = 400):
        return jsonify({"error": msg}), code

    #
    # HTML
    @app.route("/")
    def index():
        boot = {
            "version": __version__,
            "schema": schema_for_client(),
            "defaults": {"render_size_pct": cfg.default_render_size_pct, "target_fps": cfg.target_fps},
            "project_dir": str(cfg.project_dir),
            "dictionary_dir": str(cfg.dictionary_dir),
        }
        return render_template("index.html", boot=boot, font_size_px=cfg.font_size_px)

    #
    # Dictionary
    @app.route("/api/glosses")
    def api_glosses():
        """List of all the signs in the dictionary."""
        return jsonify({"glosses": dictionary.glosses, "hold": HOLD_KEYWORD})

    @app.route("/api/glosses/reload", methods=["POST"])
    def api_glosses_reload():
        """Re-scan the dictionary folder."""
        dictionary.reload()
        return jsonify({"count": len(dictionary.glosses)})

    @app.route("/api/glosses/durations", methods=["POST"])
    def api_gloss_durations():
        """Original durations (s) of the requested glosses. Unknown ones are computed in background (see 'job')."""
        ids = (request.get_json(silent=True) or {}).get("ids") or []
        known, missing = {}, []
        with durations.lock:
            for gid in dict.fromkeys(str(i) for i in ids):
                if gid in durations.values:
                    known[gid] = durations.values[gid]
                elif gid in dictionary and gid not in durations.errors and gid not in durations.pending:
                    missing.append(gid)
            durations.pending.update(missing)
            pending = [gid for gid in ids if gid in durations.pending]

        job = None
        if missing:
            items = [{"id": gid, "name": split_gloss_id(gid)[1], "path": str(dictionary.blend_path(gid))}
                     for gid in missing]

            def work(job: Job):
                try:
                    runner.gloss_durations(job, items, lambda r: durations.store(r["id"], r.get("secs"), r.get("error")))
                finally:
                    with durations.lock:
                        durations.pending.difference_update(missing)
                    durations.save()

            job = aux_queue.submit(Job("durations", f"Durations of {len(items)} sign(s)"), work)
        return jsonify({"durations": known, "pending": pending, "job": job.to_dict() if job else None})

    @app.route("/api/glosses/preview", methods=["POST"])
    def api_gloss_preview():
        """Video preview of a single sign. Returns its URL if available, otherwise starts a job to render it."""
        gloss_id = str((request.get_json(silent=True) or {}).get("id", "")).strip()
        if gloss_id not in dictionary:
            return bad_request(f"Sign '{gloss_id}' is not in the dictionary.", 404)

        out = preview_path(gloss_id)
        if out.exists():
            return jsonify({"status": "ready", "url": preview_url(gloss_id)})

        def work(job: Job):
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp_mp4 = out.with_name(f".{out.stem}-{job.id}.mp4")
            tmp_mms = out.with_name(f".{out.stem}-{job.id}{MMS_SUFFIX}")
            try:
                write_mms_file(tmp_mms, [{"maingloss": gloss_id, "framestart": "0", "frameend": "0",
                                          "duration": "100%", "transition": "0.3"}], [])
                runner.render_mp4(job, tmp_mms, tmp_mp4, use_relative_time=True,
                                  render_size_pct=cfg.preview_size_pct, expected_gloss_loads=1,
                                  target_fps=cfg.target_fps)
                tmp_mp4.replace(out)
                job.result = {"url": preview_url(gloss_id)}
            finally:
                for p in (tmp_mp4, tmp_mms):
                    p.unlink(missing_ok=True)

        job = aux_queue.submit(Job("preview", f"Preview of {gloss_id}", key=f"preview:{gloss_id}"), work)
        return jsonify({"status": "pending", "job": job.to_dict()})

    @app.route("/media/previews/<cls>/<filename>")
    def media_preview(cls: str, filename: str):
        return send_from_directory(previews_dir / safe_file_stem(cls), filename, max_age=3600)

    #
    # Projects (MMS instances)
    def list_mms(folder: Path):
        if not folder.is_dir():
            return []
        files = sorted((p for p in folder.iterdir() if p.is_file() and p.name.endswith(".csv")
                        and not p.name.startswith(".")), key=lambda p: p.name.lower())
        return [{"name": p.name, "modified": p.stat().st_mtime, "size": p.stat().st_size} for p in files]

    def load_mms(folder: Path, name: str):
        if "/" in name or "\\" in name or name.startswith("."):
            abort(400)
        path = folder / name
        if not path.is_file():
            abort(404)
        try:
            data = read_mms_file(path)
        except Exception as e:
            return bad_request(f"Can not read '{name}': {e}")
        data["name"] = name
        return jsonify(data)

    @app.route("/api/projects")
    def api_projects():
        """MMS instances in the project folder, plus the read-only examples of the MMS-Player."""
        return jsonify({"projects": list_mms(cfg.project_dir), "examples": list_mms(examples_dir)})

    @app.route("/api/projects/<name>")
    def api_project_get(name: str):
        """Load an MMS from the project folder."""
        return load_mms(cfg.project_dir, name)

    @app.route("/api/examples/<name>")
    def api_example_get(name: str):
        """Load one of the MMS examples of the player."""
        return load_mms(examples_dir, name)

    @app.route("/api/projects/<name>", methods=["PUT"])
    def api_project_put(name: str):
        """Save an MMS into the project folder. Body: {rows, extra_columns, overwrite}."""
        body = request.get_json(silent=True) or {}
        try:
            name = normalize_mms_name(name)
            rows = clean_rows(body.get("rows"))
        except ValueError as e:
            return bad_request(str(e))
        path = cfg.project_dir / name
        if path.exists() and not body.get("overwrite"):
            return bad_request(f"'{name}' already exists.", 409)
        write_mms_file(path, rows, [str(c) for c in body.get("extra_columns") or []])
        return jsonify({"name": name, "saved": True})

    @app.route("/api/mms/parse", methods=["POST"])
    def api_mms_parse():
        """Parse an uploaded MMS (field 'file') and return its table."""
        f = request.files.get("file")
        if f is None:
            return bad_request("No file uploaded.")
        try:
            data = parse_mms(f.read().decode("utf-8", errors="replace"))
        except ValueError as e:
            return bad_request(str(e))
        data["name"] = f.filename or "imported" + MMS_SUFFIX
        return jsonify(data)

    @app.route("/api/mms/serialize", methods=["POST"])
    def api_mms_serialize():
        """Convert a table into MMS CSV text (for download)."""
        body = request.get_json(silent=True) or {}
        try:
            rows = clean_rows(body.get("rows"))
        except ValueError as e:
            return bad_request(str(e))
        return app.response_class(serialize_mms(rows, body.get("extra_columns") or []), mimetype="text/csv")

    #
    # Generation
    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        """Render the posted MMS table into an MP4 video. Returns the job to poll."""
        body = request.get_json(silent=True) or {}
        try:
            rows = clean_rows(body.get("rows"))
        except ValueError as e:
            return bad_request(str(e))
        if not rows:
            return bad_request("The MMS has no rows.")
        opts = body.get("options") or {}
        relative = bool(body.get("relative", True))
        size_pct = int(opts.get("render_size_pct") or cfg.default_render_size_pct)
        size_pct = max(5, min(100, size_pct))
        target_fps = int(opts.get("target_fps") or cfg.target_fps)
        gloss_panel = bool(opts.get("gloss_panel"))

        try:
            stem = normalize_mms_name(body.get("name") or "untitled")[: -len(MMS_SUFFIX)]
        except ValueError:
            stem = "untitled"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_stem = f"{safe_file_stem(stem)}-{stamp}"
        mms_path = renders_dir / (out_stem + MMS_SUFFIX)
        mp4_path = renders_dir / (out_stem + ".mp4")
        write_mms_file(mms_path, rows, [str(c) for c in body.get("extra_columns") or []])

        def work(job: Job):
            runner.render_mp4(job, mms_path, mp4_path, use_relative_time=relative, render_size_pct=size_pct,
                              expected_gloss_loads=count_gloss_loads(rows, HOLD_KEYWORD),
                              target_fps=target_fps, gloss_panel=gloss_panel)
            job.result = {"url": f"/media/renders/{mp4_path.name}", "name": mp4_path.name,
                          "mms": mms_path.name}

        job = render_queue.submit(Job("render", f"Render of {stem}"), work)
        return jsonify({"job": job.to_dict()})

    @app.route("/api/renders")
    def api_renders():
        """Previously rendered videos, newest first."""
        vids = sorted(renders_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return jsonify({"renders": [{
            "name": p.name,
            "url": f"/media/renders/{p.name}",
            "mms": p.with_suffix("").name + MMS_SUFFIX if (renders_dir / (p.with_suffix("").name + MMS_SUFFIX)).exists() else None,
            "modified": p.stat().st_mtime,
        } for p in vids[:100]]})

    @app.route("/api/renders/<name>/mms")
    def api_render_mms(name: str):
        """The MMS used to produce a render."""
        return load_mms(renders_dir, name)

    @app.route("/media/renders/<filename>")
    def media_render(filename: str):
        return send_from_directory(renders_dir, filename)

    #
    # Jobs
    @app.route("/api/jobs/<job_id>")
    def api_job(job_id: str):
        """Status and progress of a background job. Add ?log=1 to get the process output."""
        job = find_job(job_id)
        if job is None:
            abort(404)
        return jsonify(job.to_dict(with_log=request.args.get("log") == "1"))

    @app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
    def api_job_cancel(job_id: str):
        """Cancel a queued or running job."""
        job = render_queue.cancel(job_id) or aux_queue.cancel(job_id)
        if job is None:
            abort(404)
        return jsonify(job.to_dict())

    @app.route("/api")
    def api_index():
        """This list of endpoints."""
        endpoints = []
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api"):
                continue
            methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
            doc = (app.view_functions[rule.endpoint].__doc__ or "").strip()
            endpoints.append({"path": rule.rule, "methods": methods, "description": doc})
        return jsonify({"endpoints": sorted(endpoints, key=lambda e: e["path"])})

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return bad_request("Not found.", 404)
        return "Not found", 404

    return app
