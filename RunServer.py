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
from pathlib import Path
import subprocess

from tempfile import TemporaryDirectory

from flask import Flask, request

BLENDER_EXE = os.getenv('BLENDER_EXE')
if BLENDER_EXE is None:
    raise Exception("Environment variable BLENDER_EXE is not set.")

CORPUS_DIR = os.getenv("AVASAG_CORPUS_DIR")
if CORPUS_DIR is None:
    raise Exception("Environment variable AVASAG_CORPUS_DIR is not set.")


GENERATED_CORPUS_PATH = Path(CORPUS_DIR) / "generated"

if not GENERATED_CORPUS_PATH.exists():
    raise Exception(f"Generated dir in Corpus path '{GENERATED_CORPUS_PATH}' doesn't exist.")


#
# Initialize the Flask server
print("Creating server...")
app = Flask(__name__)


@app.route("/")
def home():
    return '<p>MMS-Player rendering service in running. Please, check the docs for using the API.</p>'


# @app.route("/api/<filename>/<is_complete>/<is_custom>")
@app.route("/api/corpus/sentence/animation/<sentence_number>/")
# (Deprecated) Kept for backwards compatibility
@app.route("/api/<filename>", defaults={"is_complete": True, "is_custom": False})
def animation_get(sentence_number):
    filepath = GENERATED_CORPUS_PATH / "mms" / (sentence_number + ".mms")
    print(f"GET: Generating for file '{filepath}'")
    return generate_json_animation_data(mms_filepath=filepath, use_relative_time=False)


@app.route("/api/mms/animation", methods=["POST"])
def fetch_json_from_file():

    # print("Files in request: ", len(request.files))
    # for i, fname in enumerate(request.files):
    #     print(i, fname)

    file = request.files["file"]
    filename = file.filename

    tmp_dir = TemporaryDirectory(prefix="MMSserver", suffix="MMSfile")
    tmp_path = Path(tmp_dir.name)
    save_path = tmp_path / filename
    print("Saving file..... {}".format(save_path))
    file.save(save_path)
    print("File saved. Converting ...")

    return generate_json_animation_data(save_path, True)


def generate_json_animation_data(mms_filepath, use_relative_time):

    tmp_dir = TemporaryDirectory(prefix="MMSserver")
    tmp_path = Path(tmp_dir.name)

    # Convert /path/to/file.mms --> /tmp/path/to/file.blend
    export_blend_path = tmp_path / mms_filepath.with_suffix(".blend").name

    # Synthesize the MMS and save it into a temporary .blend scene file.
    print("Exporting to", export_blend_path)
    args = [
        BLENDER_EXE,
        "--background",
        "--python",
        "main.py",
        "--",
        "--source-mms-file",
        str(mms_filepath),
        "--corpus-generated-directory",
        str(GENERATED_CORPUS_PATH),
        "--export-blend",
        str(export_blend_path),
    ]
    if use_relative_time:
        args.extend(["--use-relative-time"])

    p = subprocess.Popen(args)
    p.wait()

    if not export_blend_path.exists():
        raise Exception(f"File '{str(export_blend_path)} was not generated.")

    # Export the blend scene as JSON animation data
    json_path = export_blend_path.with_suffix(".json")  # f"/tmp/sentence_{str(mms_filepath)}.json"
    p = subprocess.Popen(
        [
            BLENDER_EXE,
            "--background",
            "--python",
            "exporter/json_exporter.py",
            "--",
            "--blend-path",
            str(export_blend_path),
            "--json-path",
            json_path,
        ]
    )
    # print the stdout from the process
    p.wait()
    with open(json_path, "r") as fstream:
        string = json.load(fstream)

    return string


#
# MAIN
#
if __name__ == '__main__':
    app.run(debug=True, port=5000)
