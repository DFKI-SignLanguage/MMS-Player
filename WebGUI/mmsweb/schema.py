"""Column layout of the MMS, as presented by the web editor.

The MMS is organized in three sections (sign sequence, timing, inflections).
Each section contains subsections (e.g., one per body part for inflections),
and each subsection contains column groups. A group with more than one column
is a set of x/y/z components that the GUI can show expanded or collapsed.

Inflection columns are also organized in "fill groups", mirroring the inflection
groups of the MMS-Player (player/mms_parser.py, INFLECTION_GROUPS, which can't be
imported here since it requires Blender's mathutils). A group is applied to a row
only if at least one of its x/y/z triples is filled; its empty triples default to
identity values. The only requirement of the MMS-Player is that the x/y/z columns
of a triple are either all filled or all empty.
"""

import re
from typing import Dict, List


def _xyz(prefix: str, infix: str = "") -> List[str]:
    return [f"{prefix}{infix}{axis}" for axis in "xyz"]


def _group(gid: str, label: str, columns: List[str], unit: str = "", hint: str = "") -> dict:
    return {"id": gid, "label": label, "columns": columns, "unit": unit, "hint": hint}


def _hand_subsection(prefix: str, label: str) -> dict:
    reloc = _xyz(f"{prefix}handreloc")
    reloca = _xyz(f"{prefix}handreloc", "a")
    relocs = _xyz(f"{prefix}handreloc", "s")
    rot = _xyz(f"{prefix}handrot")
    return {
        "id": f"{prefix}hand",
        "label": label,
        "groups": [
            _group(f"{prefix}handreloc", "Traj. location", reloc, "cm", "Translation of the hand trajectory."),
            _group(f"{prefix}handreloca", "Traj. rotation", reloca, "rad", "Rotation of the hand trajectory around its starting point."),
            _group(f"{prefix}handrelocs", "Traj. scale", relocs, "×", "Scaling of the hand trajectory around its starting point."),
            _group(f"{prefix}handrot", "Hand rotation", rot, "rad", "Delta rotation applied to the hand bone."),
        ],
        "fill_groups": [reloc + reloca + relocs, rot],
    }


SECTIONS: List[dict] = [
    {
        "id": "sequence",
        "label": "Sign sequence",
        "subsections": [
            {
                "id": "glosses",
                "label": "Glosses",
                "groups": [
                    _group("maingloss", "Main gloss", ["maingloss"], "", "Gloss played on the full body (or <HOLD>)."),
                    _group("domarm", "Dom. arm", ["domarm"], "", "Optional gloss (or <HOLD>) overriding the dominant arm."),
                    _group("ndomarm", "Non-dom. arm", ["ndomarm"], "", "Optional gloss (or <HOLD>) overriding the non-dominant arm."),
                ],
                "fill_groups": [],
            },
        ],
    },
    {
        "id": "timing",
        "label": "Timing",
        "subsections": [
            {
                "id": "absolute",
                "label": "Absolute",
                "groups": [
                    _group("framestart", "Start", ["framestart"], "s", "Absolute start time of the sign, in seconds."),
                    _group("frameend", "End", ["frameend"], "s", "Absolute end time of the sign, in seconds."),
                ],
                "fill_groups": [],
            },
            {
                "id": "relative",
                "label": "Relative",
                "groups": [
                    _group("transition", "Transition", ["transition"], "s", "Time from the end of the previous sign."),
                    _group("duration", "Duration", ["duration"], "s | %", "Duration in seconds, or speed as percentage of the original (e.g. 100%)."),
                ],
                "fill_groups": [],
            },
        ],
    },
    {
        "id": "inflections",
        "label": "Inflections",
        "subsections": [
            {
                "id": "torso",
                "label": "Torso",
                "groups": [
                    _group("torsoreloc", "Location", _xyz("torsoreloc"), "cm"),
                    _group("torsoreloca", "Rotation", _xyz("torsoreloc", "a"), "rad"),
                ],
                "fill_groups": [_xyz("torsoreloc") + _xyz("torsoreloc", "a")],
            },
            {
                "id": "head",
                "label": "Head",
                "groups": [
                    _group("headrot", "Rotation", _xyz("headrot"), "rad"),
                ],
                "fill_groups": [_xyz("headrot")],
            },
            {
                "id": "shoulders",
                "label": "Shoulders",
                "groups": [
                    _group("domshoulderreloc", "Dom. offset", _xyz("domshoulderreloc"), "cm"),
                    _group("ndomshoulderreloc", "Non-dom. offset", _xyz("ndomshoulderreloc"), "cm"),
                ],
                "fill_groups": [_xyz("domshoulderreloc"), _xyz("ndomshoulderreloc")],
            },
            _hand_subsection("dom", "Dominant hand"),
            _hand_subsection("ndom", "Non-dominant hand"),
        ],
    },
]

HOLD_KEYWORD = "<HOLD>"
GLOSS_COLUMNS = ["maingloss", "domarm", "ndomarm"]

# The columns that are always written, in the order used by the MMS examples.
BASE_COLUMNS = ["maingloss", "framestart", "frameend", "duration", "transition", "domarm", "ndomarm"]

FILL_GROUPS: List[List[str]] = [fg for sec in SECTIONS for sub in sec["subsections"] for fg in sub["fill_groups"]]

INFLECTION_COLUMNS: List[str] = [c for fg in FILL_GROUPS for c in fg]

KNOWN_COLUMNS: List[str] = BASE_COLUMNS + INFLECTION_COLUMNS

_SCALE_RE = re.compile(r"relocs[xyz]$")


def identity_value(column: str) -> str:
    """The value of an inflection column that leaves the animation untouched."""
    return "1" if _SCALE_RE.search(column) else "0"


def schema_for_client() -> dict:
    return {
        "sections": SECTIONS,
        "base_columns": BASE_COLUMNS,
        "gloss_columns": GLOSS_COLUMNS,
        "fill_groups": FILL_GROUPS,
        "identity": {c: identity_value(c) for c in INFLECTION_COLUMNS},
        "hold": HOLD_KEYWORD,
    }


def columns_to_write(rows: List[Dict[str, str]], extra_columns: List[str]) -> List[str]:
    """Selects the columns to write: the base columns, the inflection fill groups
    that have at least one value, and any extra (unknown) column loaded from a file."""

    def has_values(cols: List[str]) -> bool:
        return any((row.get(c) or "").strip() != "" for row in rows for c in cols)

    out = list(BASE_COLUMNS)
    for fg in FILL_GROUPS:
        if has_values(fg):
            out.extend(fg)
    out.extend(c for c in extra_columns if c not in out)
    return out
