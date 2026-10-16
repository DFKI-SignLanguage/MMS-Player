"""Index of the signs available in the Dictionary.

The dictionary is organized as <dictionary_dir>/<class>/trimmed/<NAME>.blend.
In the MMS, a sign is referred to as <class>:<NAME>, or simply as <NAME> for the default class "signs".
"""

from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_SIGN_CLASS = "signs"


def split_gloss_id(gloss_id: str) -> Tuple[str, str]:
    """Returns (class, name) for a gloss id as written in the MMS."""
    if ":" in gloss_id:
        cls, name = gloss_id.split(":", 1)
        return cls, name
    return DEFAULT_SIGN_CLASS, gloss_id


def make_gloss_id(cls: str, name: str) -> str:
    return name if cls == DEFAULT_SIGN_CLASS else f"{cls}:{name}"


class Dictionary:

    def __init__(self, root: Path):
        self.root = root
        self.glosses: List[dict] = []
        self.reload()

    def reload(self) -> None:
        glosses = []
        for cls_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            trimmed = cls_dir / "trimmed"
            if not trimmed.is_dir():
                continue
            for blend in sorted(trimmed.glob("*.blend")):
                glosses.append({
                    "id": make_gloss_id(cls_dir.name, blend.stem),
                    "cls": cls_dir.name,
                    "name": blend.stem,
                })
        self.glosses = glosses
        self._ids = {g["id"] for g in glosses}

    def __contains__(self, gloss_id: str) -> bool:
        return gloss_id in self._ids

    def blend_path(self, gloss_id: str) -> Optional[Path]:
        """Path of the .blend file of the gloss, or None if it isn't in the dictionary."""
        if gloss_id not in self._ids:
            return None
        cls, name = split_gloss_id(gloss_id)
        return self.root / cls / "trimmed" / f"{name}.blend"
