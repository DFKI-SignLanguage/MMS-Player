"""Server options persisted in a local JSON file, so they don't need to be repeated at every start."""

import json
from pathlib import Path

DEFAULT_OPTIONS = {
    "target_fps": 30,
    "font_size_px": 13,  # base font size of the web interface; all the other sizes scale with it
}


def load_options(path: Path) -> dict:
    """Returns the defaults overridden by the values stored in the file (if it exists)."""
    options = dict(DEFAULT_OPTIONS)
    if path.exists():
        options.update(json.loads(path.read_text()))
    return options


def save_options(path: Path, options: dict) -> None:
    path.write_text(json.dumps(options, indent=2) + "\n")
