"""Reading and writing MMS instances (CSV files)."""

import csv
import io
import re
from pathlib import Path
from typing import Dict, List

from .schema import KNOWN_COLUMNS, columns_to_write

MMS_SUFFIX = ".mms.csv"

ABSOLUTE_TIME_COLUMNS = ("framestart", "frameend")

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ +-]*$")


def normalize_mms_name(name: str) -> str:
    """Validates a project file name and ensures it ends with .mms.csv.
    Raises ValueError for names that are not plain file names."""

    name = (name or "").strip()
    if name.endswith(MMS_SUFFIX):
        stem = name[: -len(MMS_SUFFIX)]
    elif name.endswith(".csv"):
        stem = name[: -len(".csv")]
    else:
        stem = name
    if not stem or not _NAME_RE.match(stem) or ".." in stem:
        raise ValueError(f"Invalid MMS name '{name}'. Use letters, digits, spaces, and . _ + - only.")
    return stem + MMS_SUFFIX


def parse_mms(text: str) -> dict:
    """Parses the CSV text of an MMS into {columns, extra_columns, rows, relative}."""

    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    data = [r for r in reader if any(cell.strip() for cell in r)]
    if not data:
        raise ValueError("The MMS file is empty.")

    header = [h.strip() for h in data[0]]
    if "maingloss" not in header:
        raise ValueError("The MMS file has no 'maingloss' column.")

    rows: List[Dict[str, str]] = []
    for raw in data[1:]:
        row = {}
        for i, col in enumerate(header):
            if col == "":
                continue
            row[col] = raw[i].strip() if i < len(raw) else ""
        rows.append(row)

    extra = [c for c in header if c and c not in KNOWN_COLUMNS]

    return {
        "columns": header,
        "extra_columns": extra,
        "rows": rows,
        "relative": guess_relative_time(rows),
    }


def guess_relative_time(rows: List[Dict[str, str]]) -> bool:
    """The MMS doesn't store whether relative timing is used.
    Guess it: relative if any duration is specified, absolute if only frame start/end are."""

    def filled(row, col):
        v = (row.get(col) or "").strip()
        return v not in ("", "0", "0.0")

    if any(filled(r, "duration") for r in rows):
        return True
    if any(filled(r, "framestart") or filled(r, "frameend") for r in rows):
        return False
    return True


def serialize_mms(rows: List[Dict[str, str]], extra_columns: List[str]) -> str:
    columns = columns_to_write(rows, extra_columns)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        values = [str(row.get(c, "") or "").strip() for c in columns]
        # The player parses framestart/frameend also when using relative timing.
        values = [("0" if v == "" and c in ABSOLUTE_TIME_COLUMNS else v) for c, v in zip(columns, values)]
        writer.writerow(values)
    return out.getvalue()


def read_mms_file(path: Path) -> dict:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return parse_mms(f.read())


def write_mms_file(path: Path, rows: List[Dict[str, str]], extra_columns: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(serialize_mms(rows, extra_columns))


def clean_rows(raw_rows) -> List[Dict[str, str]]:
    """Sanitizes rows coming from the client."""
    if not isinstance(raw_rows, list):
        raise ValueError("'rows' must be a list.")
    rows = []
    for r in raw_rows:
        if not isinstance(r, dict):
            raise ValueError("Each row must be an object.")
        rows.append({str(k): ("" if v is None else str(v)).strip() for k, v in r.items()})
    return rows
