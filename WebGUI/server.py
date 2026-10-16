#!/usr/bin/env python3
"""MMS-Player Web GUI server.

Example:
    python server.py --dictionary-dir path/to/DictionaryGeneration-deploy-YYMMDD --project-dir path/to/my-project
"""

import argparse
import os
import sys
from pathlib import Path

from mmsweb.app import ServerConfig, create_app
from mmsweb.options import load_options, save_options

WEBGUI_DIR = Path(__file__).resolve().parent
SERVER_OPTIONS_PATH = WEBGUI_DIR / "server_options.local.json"


def main():
    parser = argparse.ArgumentParser(description="Web interface to edit MMS instances and render them with the MMS-Player.")
    parser.add_argument("--dictionary-dir", default=os.getenv("DICTIONARY_DIR"),
                        help="Folder of the Dictionary of signs (default: $DICTIONARY_DIR).")
    parser.add_argument("--player-dir", default=str(WEBGUI_DIR.parent),
                        help="Folder of the MMS-Player, containing main.py (default: the parent folder).")
    parser.add_argument("--project-dir", required=True,
                        help="Folder where the MMS instances, renders, and caches are stored. Created if missing.")
    parser.add_argument("--blender-exe", default=os.getenv("BLENDER_EXE"),
                        help="Path to the Blender executable (default: $BLENDER_EXE).")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 to accept connections from other machines.")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--render-workers", type=int, default=1, help="Number of videos rendered in parallel.")
    parser.add_argument("--preview-size-pct", type=int, default=25, help="Render size of the sign previews (%%).")
    parser.add_argument("--render-size-pct", type=int, default=50, help="Default render size of the generated videos (%%).")
    parser.add_argument("--target-fps", type=int, default=None,
                        help=f"Default FPS of the generated videos (default: 30). "
                             f"The value is saved in {SERVER_OPTIONS_PATH.name} and reused at the next start.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    def fail(msg):
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    if not args.dictionary_dir:
        fail("Specify the dictionary with --dictionary-dir or the DICTIONARY_DIR env variable.")
    if not args.blender_exe:
        fail("Specify the Blender executable with --blender-exe or the BLENDER_EXE env variable.")

    # Options persisted across runs: the command line overrides (and updates) the stored values.
    options = load_options(SERVER_OPTIONS_PATH)
    if args.target_fps is not None:
        if args.target_fps <= 0:
            fail("--target-fps must be a positive number.")
        options["target_fps"] = args.target_fps
    if float(options["font_size_px"]) <= 0:
        fail(f"font_size_px in {SERVER_OPTIONS_PATH.name} must be a positive number.")
    save_options(SERVER_OPTIONS_PATH, options)

    cfg = ServerConfig(
        dictionary_dir=Path(args.dictionary_dir).expanduser().resolve(),
        player_dir=Path(args.player_dir).expanduser().resolve(),
        project_dir=Path(args.project_dir).expanduser().resolve(),
        blender_exe=Path(args.blender_exe).expanduser(),
        render_workers=max(1, args.render_workers),
        preview_size_pct=args.preview_size_pct,
        default_render_size_pct=args.render_size_pct,
        target_fps=int(options["target_fps"]),
        font_size_px=float(options["font_size_px"]),
    )

    if not cfg.dictionary_dir.is_dir():
        fail(f"Dictionary folder '{cfg.dictionary_dir}' doesn't exist.")
    if not (cfg.player_dir / "main.py").is_file():
        fail(f"'{cfg.player_dir}' doesn't contain the MMS-Player main.py.")
    if not cfg.blender_exe.is_file():
        fail(f"Blender executable '{cfg.blender_exe}' doesn't exist.")

    app = create_app(cfg)
    print(f"Dictionary: {cfg.dictionary_dir}")
    print(f"MMS-Player: {cfg.player_dir}")
    print(f"Project:    {cfg.project_dir}")
    print(f"Blender:    {cfg.blender_exe}")
    print(f"Target FPS: {cfg.target_fps} (from {SERVER_OPTIONS_PATH.name})")
    print(f"Open http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
