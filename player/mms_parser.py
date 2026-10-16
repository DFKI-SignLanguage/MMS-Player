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

#
# Parse the mms and trim the motion capture data from the library.
#

import csv
import mathutils

from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple, Dict, List


DEFAULT_SIGN_TYPE = "signs"

HOLD_KEYWORD = "<HOLD>"

# Maps each inflection group to the prefixes of its x/y/z column triples.
# A group is applied to a row only if at least one of its triples is filled in that row.
INFLECTION_GROUPS: Dict[str, List[str]] = {
    "torso": ["torsoreloc", "torsoreloca"],
    "head": ["headrot"],
    "domshoulder": ["domshoulderreloc"],
    "ndomshoulder": ["ndomshoulderreloc"],
    "domhandreloc": ["domhandreloc", "domhandreloca", "domhandrelocs"],
    "domhandrot": ["domhandrot"],
    "ndomhandreloc": ["ndomhandreloc", "ndomhandreloca", "ndomhandrelocs"],
    "ndomhandrot": ["ndomhandrot"],
}


class GlossInfo:
    """The content of a (n)domarm cell: either another gloss to play on the arm bones, or a <HOLD>."""

    def __init__(self, column: str, name: Optional[str] = None, datatype: Optional[str] = None, is_hold: bool = False):
        assert (is_hold and name is None and datatype is None) \
          or (not is_hold and name is not None and datatype is not None)
        self.column = column
        self.name = name  # The gloss to play on the arm. None if is_hold.
        self.datatype = datatype  # The class/type of the gloss. None if is_hold.
        self.is_hold = is_hold  # If True, the arm freezes at the last pose of the previous row.

    def __repr__(self):
        return "GlossInfo(<HOLD>)" if self.is_hold else f"GlossInfo({self.datatype}:{self.name})"

    def to_compact_string(self) -> str:
        if self.is_hold:
            out = "<HOLD>"
        else:
            assert self.name is not None
            out = self.name

        return self.column + ":" + out


class MMSLine:
    """MMSLine represents a single row of the MMS table.
    
    Since each row in the table associates to a different sign necessary to 
    be inflected, the class functions to store and retrieve the data required
    for the inflection of the corresponding sign.
    """

    def __init__(self, column_indices: Dict[str, int], line_data: List[Optional[str]], gloss_idx: int):

        self.column_indices_dict = column_indices  # Maps the column name to its index within the MMS row.
        self.line_data = line_data  # The full row of the MMS in text format.
        self.idx = gloss_idx  # The sequential row number in the MMS, from 0.

        # Parse the main gloss
        maingloss_idx = self.column_indices_dict["maingloss"]
        
        main_gloss_info = self.parse_gloss_info(column="maingloss", cell_content=line_data[maingloss_idx])
        if main_gloss_info is None:
            raise Exception(f"Row {self.idx}: maingloss can not be empty.")

        self.maingloss_info: GlossInfo = main_gloss_info

        self.output_name = f"{gloss_idx}_" + self.maingloss_info.to_compact_string()  # A string composing the row counter with the gloss name

        # Parse the arm overrides
        domarm_idx = self.column_indices_dict["domarm"]
        self.domarm_info: Optional[GlossInfo] = self.parse_gloss_info(column="domarm", cell_content=line_data[domarm_idx])
        ndomarm_idx = self.column_indices_dict["ndomarm"]
        self.ndomarm_info: Optional[GlossInfo] = self.parse_gloss_info(column="ndomarm", cell_content=line_data[ndomarm_idx])


    def __getitem__(self, key):
        return self.line_data[self.column_indices_dict[key]]

    def get(self, key) -> Optional[str]:
        """Like [key], but returns None if the column is missing or the cell is empty/blank."""
        if key not in self.column_indices_dict:
            return None
        idx = self.column_indices_dict[key]
        if idx >= len(self.line_data):
            return None
        value = self.line_data[idx]
        if value is None or value.strip() == "":
            return None
        return value

    def __repr__(self):
        return f"(MMSLine {self.column_indices_dict} for {self.maingloss_info})"

    def keys(self):
        return list(self.column_indices_dict.keys())

    @staticmethod
    def parse_gloss_info(column: str, cell_content: Optional[str]) -> Optional[GlossInfo]:
        """Builds a GlossInfo instance from parsing a not-None string taken from a gloss column.
        If the input is None, outputs None as well. Otherwise parses the gloss info."""

        # None input makes None Output
        if cell_content is None:
            return None

        # Empty strings are like None
        cell_content = cell_content.strip()
        if cell_content == "":
            return None

        # If it is a <HOLD>, return immediately
        if cell_content == HOLD_KEYWORD:
            return GlossInfo(column=column, is_hold=True)

        # If there is no column, use the default gloss type
        if ":" not in cell_content:
            return GlossInfo(column=column, name=cell_content, datatype=DEFAULT_SIGN_TYPE)

        # Default case: the type is specified
        split = cell_content.split(":")
        if len(split) == 2:
            return GlossInfo(column=column, name=split[1], datatype=split[0])

        raise Exception(f"Format error for gloss entry '{cell_content}'")

    def handle_none(self, key) -> Optional[Tuple[float, float, float]]:
        """Retrieves the 3 values of the key + x/y/z.
          If all of them are empty (or the columns are missing), returns None.
          If only some of them are empty, raises an exception."""

        x = self.get(key + "x")
        y = self.get(key + "y")
        z = self.get(key + "z")

        if x is None and y is None and z is None:
            return None

        if x is None or y is None or z is None:
            raise Exception(f"Row {self.idx}: columns {key}x/y/z must be either all filled or all empty (found x={x}, y={y}, z={z}).")

        return float(x), float(y), float(z)

    def has_inflection(self, group: str) -> bool:
        """True if at least one of the column triples of the given inflection group (see INFLECTION_GROUPS) is filled in this row."""
        return any(self.handle_none(prefix) is not None for prefix in INFLECTION_GROUPS[group])

    def traj_rotation(self, dominance: str) -> Optional[mathutils.Matrix]:
        """Rotation of the hand trajectory.

        @type dominance: str
        @param dominance: The dominance of the hand.
        """
        values = self.handle_none(f"{dominance}handreloca")
        if values is None:
            return None
        return mathutils.Euler(values, "ZXY").to_matrix().to_4x4()

    def hand_orientation(self, dominance) -> Optional[mathutils.Quaternion]:
        """Hand Orientation.

        @type dominance: str
        @param dominance: The dominance of the hand.
        """
        values = self.handle_none(f"{dominance}handrot")
        if values is None:
            return None
        return mathutils.Euler(values, "ZXY").to_quaternion()

    def translation(self, dominance) -> Optional[mathutils.Matrix]:
        """Translation of the hand trajectory.

        @type dominance: str
        @param dominance: The dominance of the hand.
        """
        values = self.handle_none(f"{dominance}handreloc")
        if values is None:
            return None
        return mathutils.Matrix.Translation(values)

    def scale(self, dominance) -> Optional[mathutils.Matrix]:
        """Scale of the hand trajectory.

        @type dominance: str
        @param dominance: The dominance of the hand.
        """
        values = self.handle_none(f"{dominance}handrelocs")
        if values is None:
            return None
        scale = mathutils.Matrix.Identity(4)
        scale[0][0] = values[0]
        scale[1][1] = values[1]
        scale[2][2] = values[2]
        return scale

    def timing(self) -> Tuple[float, float]:
        """Start and the end frame of the gloss in the timeline."""
        return float(self["framestart"]), float(self["frameend"])

    def head_rot(self) -> Optional[mathutils.Quaternion]:
        """Rotation of the head."""
        values = self.handle_none(f"headrot")
        if values is None:
            return None
        return mathutils.Euler(values, "ZXY").to_quaternion()

    def shoulder_shift(self, dominance) -> Optional[mathutils.Matrix]:
        """Translation of the shoulders.

        @type dominance: str
        @param dominance: The dominance of the hand.
        """
        values = self.handle_none(f"{dominance}shoulderreloc")
        if values is None:
            return None
        return mathutils.Matrix.Translation(values)

    def torso_shift(self) -> Optional[mathutils.Matrix]:
        """Translation of the torso."""
        values = self.handle_none(f"torsoreloc")
        if values is None:
            return None
        return mathutils.Matrix.Translation(values)

    def torso_rot(self) -> Optional[mathutils.Quaternion]:
        """Rotation of the torso."""
        values = self.handle_none(f"torsoreloca")
        if values is None:
            return None
        return mathutils.Euler(values, "ZXY").to_quaternion()

    def transition(self) -> float:
        """Number of seconds from the previous gloss. Used only in relative_time mode."""

        return float(self["transition"])

    def duration(self) -> Tuple[float, bool]:
        """Number of frames in the gloss.
        :returns: A 2-tuple.
        The first value is the duration, either:
          i) absolute value, in seconds; or
          ii) ratio of the original duration, in range [0.0,1.0].
        The second value is True if the duration is a ratio (case ii)."""

        duration = self["duration"]
        if "%" in duration:
            time = duration.strip("%")
            time_ratio = float(time) / 100.0
            return time_ratio, True
        else:
            return float(duration), False


class MMS:
    """MMS table representation.
    
    Attributes:
        rows_map: the MMS table which is an ordered dict of items sorted according to time. key = tuple(int, str), key = MMSLine
        row_indices: A list of time-ordered indices of the mms rows: List[Tuple[int, str]]
        inflections_availability_dict: Contains the information if given mms data is present or not.
    """

    def __init__(self,
                 rows: Dict[Tuple[int, str], MMSLine],
                 inflections_availability: Dict[str, bool]):

        self.rows_map: Dict[Tuple[int, str], MMSLine] = rows
        self.row_indices: List[Tuple[int, str]] = list(rows.keys())
        self.inflections_availability_dict: Dict[str, bool] = inflections_availability

    def __getitem__(self, key: Tuple[int, str]) -> MMSLine:
        """Access the MMS line using the given key."""
        if key not in self.rows_map:
            raise KeyError(f"{key} not found in the mms")
        return self.rows_map[key]

    def __repr__(self):
        return f"MMS({self.row_indices})"


class MMSParser:
    """The parser for MMS data."""

    def __init__(self, mms_file: Path):
        self._mms_file = mms_file

    def parse(self) -> MMS:
        """Parse the mms file and return the MMS object.
        
        In order to parse the data:
        1. Read the CSV file consisting the MMS data.
        2.
        """
        with open(self._mms_file, "r") as read_stream:
            reader = csv.reader(read_stream, delimiter=",")
            data = list(reader)

        # Maps the column name of the CSV into index.
        # This allows to access the row information.
        index_for_column = {}
        for i, column in enumerate(data[0]):
            index_for_column[column] = i

        # Store the availability information: a group is available if at least one of its column triples is in the header.
        # Whether it is actually applied is then decided row by row (see MMSLine.has_inflection()).
        inflections_availability = {
            group: any(prefix + "x" in data[0] for prefix in prefixes)
            for group, prefixes in INFLECTION_GROUPS.items()
        }

        # Iterates on the MMS data
        rows_dict: Dict[Tuple[int, str], MMSLine] = {}
        rows_list: List[MMSLine] = []
        for idx, mms_row_str in enumerate(data[1:]):
            # Convert empty values to None.
            mms_row_str = [x if x != "" else None for x in mms_row_str]
            mms_row = MMSLine(column_indices=index_for_column, line_data=mms_row_str, gloss_idx=idx)

            if mms_row.maingloss_info is None:
                raise Exception("maingloss column can not be empty")

            # Fail early if some inflection triple is only partially filled.
            for group in INFLECTION_GROUPS:
                mms_row.has_inflection(group)

            if idx == 0:
                for gloss_info in (mms_row.maingloss_info, mms_row.domarm_info, mms_row.ndomarm_info):
                    if gloss_info is not None and gloss_info.is_hold:
                        raise Exception(f"<HOLD> can not be used in the first row of an MMS.")

            # Just a repetition of the assertion in the GlossInfo constructor
            for gloss_info in (mms_row.maingloss_info, mms_row.domarm_info, mms_row.ndomarm_info):
                if gloss_info is not None:
                    assert (gloss_info.is_hold and (gloss_info.name is None and gloss_info.datatype is None)) or \
                           (not gloss_info.is_hold and (gloss_info.name is not None and gloss_info.datatype is not None))


            # TODO -- will need to simplify this and bring gloss indexing to simple int.
            idx_name = "HOLD" if mms_row.maingloss_info else mms_row.maingloss_info.name
            rows_dict[(idx, idx_name)] = mms_row
            rows_list.append(mms_row)

        assert len(rows_dict) == len(rows_list)

        # sorts the entries according to the "framestart"
        # TODO -- actually useless if the times are given in relative mode.
        rows_ordered_dict = OrderedDict(sorted(rows_dict.items(), key=lambda x: x[1].timing()[0]))

        return MMS(rows=rows_ordered_dict, inflections_availability=inflections_availability)


# TODO -- Convert this into a test unit
# if __name__ == "__main__":
#     # Simple test to verify whether the parser is working or not
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--mms-file", type=str)
#     args = parser.parse_args()
#     args.mms_file = os.environ["AVASAG_CORPUS_DIR"] + "/generated/mms/0009.mms"
#     args.generated_root = os.environ["AVASAG_CORPUS_DIR"] + "/generated"
#     parser = MMSParser(args.mms_file)
#     parsed_mms = parser.parse()
#     for mms_gloss in parsed_mms.row_indices:
#         print("========================================")
#         print(f"Using {parsed_mms[mms_gloss].output_name}")
#         print("Timing: ", parsed_mms[mms_gloss].timing())
#         print("Translation [ Dom]: \n", parsed_mms[mms_gloss].translation("dom"))
#         print("Translation [nDom]: \n", parsed_mms[mms_gloss].translation("ndom"))

#         print("Rotation [ Dom]: \n", parsed_mms[mms_gloss].traj_rotation("dom"))
#         print("Rotation [nDom]: \n", parsed_mms[mms_gloss].traj_rotation("ndom"))

#         print("Scale [ Dom]: \n", parsed_mms[mms_gloss].scale("dom"))
#         print("Scale [nDom]: \n", parsed_mms[mms_gloss].scale("ndom"))

#         print("Shoulder Shift [ Dom]: \n", parsed_mms[mms_gloss].shoulder_shift("dom"))
#         print("Shoulder Shift [nDom]: \n", parsed_mms[mms_gloss].shoulder_shift("ndom"))

#         print("Torso [Position]: \n", parsed_mms[mms_gloss].torso_shift())
#         print("Torso [Rotation]: \n", parsed_mms[mms_gloss].torso_rot())

#         print("Head [Rotation]: \n", parsed_mms[mms_gloss].head_rot())
