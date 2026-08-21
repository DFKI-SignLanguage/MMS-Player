#    MMS Player - procedural animation of Sign Language avatars
#    Copyright (C) 2024 German Research Center for Artificial Intelligence (DFKI)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import subprocess

from tempfile import TemporaryDirectory

from flask import Flask, request
from werkzeug.utils import secure_filename

BLENDER_EXE = os.getenv('BLENDER_EXE')
if BLENDER_EXE is None:
    raise Exception("Environment variable BLENDER_EXE is not set.")

DICTIONARY_DIR = os.getenv("DICTIONARY_DIR")
if DICTIONARY_DIR is None:
    raise Exception("Environment variable DICTIONARY_DIR is not set.")


#
# Initialize the Flask server
print("Creating server...")
app = Flask(__name__)


@app.route("/")
def home():
    return '<p>MMS-Player rendering service in running. Please, check the docs for using the API.</p>'



@app.route("/api")
def api_index():
    endpoints = []
    for rule in app.url_map.iter_rules():
        if rule.rule == "/api" or not rule.rule.startswith("/api"):
            continue
        view_func = app.view_functions[rule.endpoint]
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        endpoints.append({
            "path": rule.rule,
            "methods": methods,
            "description": (view_func.__doc__ or "").strip()
        })
    endpoints.sort(key=lambda e: e["path"])
    return {"endpoints": endpoints}


@app.route("/api/mms/animation", methods=["POST"])
def fetch_json_from_file():
    """Convert an uploaded .mms file into animation JSON. Expects a multipart/form-data POST with the file under the 'file' field."""

    file = request.files["file"]

    if file.filename is None:
        raise Exception("request.files['file'].filename is None")

    mms_filename: str = secure_filename(file.filename)
    if not mms_filename:
        raise Exception(f"Uploaded filename '{file.filename}' is not valid.")

    tmp_dir = TemporaryDirectory(prefix="MMSserver", suffix="MMSfile")
    tmp_dir_path = Path(tmp_dir.name)

    mms_path = tmp_dir_path / mms_filename

    print("Saving MMS file..... {}".format(mms_path))
    file.save(mms_path)

    anim_json_path = mms_path.with_suffix(".json")

    # print("File saved. Converting ...")
    res = run_mms_player(mms_filepath=mms_path,
                         use_relative_time=True,
                         export_anim_json=anim_json_path
                         )

    with open(str(res.anim_json_path), "r") as fstream:
        out_json = json.load(fstream)

    return out_json



@dataclass
class RealizationResult:
    bvh_path: Optional[Path] = None
    fbx_path: Optional[Path] = None
    mp4_path: Optional[Path] = None
    anim_json_path: Optional[Path] = None
    blend_path: Optional[Path] = None


def run_mms_player(mms_filepath: Path, use_relative_time: bool,
                    export_bvh: Optional[Path] = None,
                    export_fbx: Optional[Path] = None,
                    export_mp4: Optional[Path] = None,
                    export_anim_json: Optional[Path] = None,
                    export_blend: Optional[Path] = None) -> RealizationResult:

    result = RealizationResult()

    args = [
        BLENDER_EXE,
        "--background",
        "--python", "main.py",
        "--",
        "--source-mms-file", str(mms_filepath),
        "--dictionary-dir", str(DICTIONARY_DIR),
    ]

    if use_relative_time:
        args.extend(["--use-relative-time"])

    if export_bvh:
        result.bvh_path = export_bvh
        args.extend(["--export-bvh", str(result.bvh_path)])
    if export_fbx:
        result.fbx_path = export_fbx
        args.extend(["--export-fbx", str(result.fbx_path)])
    if export_mp4:
        result.mp4_path = export_mp4
        args.extend(["--export-mp4", str(result.mp4_path)])
    if export_anim_json:
        result.anim_json_path = export_anim_json
        args.extend(["--export-anim-json", str(result.anim_json_path)])
    if export_blend:
        result.blend_path = export_blend
        args.extend(["--export-blend", str(result.blend_path)])

    print(f"Running MMS-Player process...")
    p = subprocess.Popen(args)
    p.wait()
    print("MMS-Player process ended.")

    for export_path in (result.bvh_path, result.fbx_path, result.mp4_path, result.anim_json_path, result.blend_path):
        if export_path is not None and not export_path.exists():
            raise Exception(f"File '{str(export_path)}' was not generated.")

    return result


def generate_json_animation_data(mms_filepath, use_relative_time):

    tmp_dir = TemporaryDirectory(prefix="MMSserver")
    tmp_path = Path(tmp_dir.name)

    # Convert /path/to/file.mms --> /tmp/path/to/file.blend
    # export_blend_path = tmp_path / mms_filepath.with_suffix(".blend").name
    export_json_path = tmp_path / mms_filepath.with_suffix(".json")

    # Synthesize the MMS and save it into a temporary .blend scene file.
    print("Exporting to", export_json_path)
    args = [
        BLENDER_EXE,
        "--background",
        "--python", "main.py",
        "--",
        "--source-mms-file", str(mms_filepath),
        "--dictionary-directory", str(DICTIONARY_DIR),
        "--export-anim-json", str(export_json_path)
    ]
    if use_relative_time:
        args.extend(["--use-relative-time"])

    p = subprocess.Popen(args)
    p.wait()

    if not export_json_path.exists():
        raise Exception(f"File '{str(export_json_path)} was not generated.")

    with open(export_json_path, "r") as fstream:
        string = json.load(fstream)

    return string


#
# MAIN
#
if __name__ == '__main__':
    app.run(debug=True, port=5000)
