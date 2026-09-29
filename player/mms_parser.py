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

import argparse
import csv
import mathutils
import math
import os
import re

from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple, Dict, List


class MMSLine:
    """MMSLine represents a single row of the MMS table.
    
    Since each row in the table associates to a different sign necessary to 
    be inflected, the class functions to store and retrieve the data required
    for the inflection of the corresponding sign.
    """

    def __init__(self, store_index: Dict[str, int], line_data: List[Optional[str]], gloss_idx: int):

        self.store_index = store_index  # Maps the column name to its index within the MMS row.
        self.line_data = line_data  # The full row of the MMS in text format.
        self.name, self.datatype = self.find_datatype(line_data[0])  # The gloss itself and its class/type (defauts to 'signs').
        self.is_hold: bool = False  # Set to true if the gloss in this lione is <HODL>. The rest of the parameters will be set to the values of the previous gloss, but during realization this flag will be used to handle the animation differently.
        self.output_name = f"{gloss_idx}_{self.name}"  # We overwrite the name.

    def __getitem__(self, key):
        return self.line_data[self.store_index[key]]

    def __repr__(self):
        return f"(MMSLine for {self.name} {self.datatype})"

    def keys(self):
        return list(self.store_index.keys())

    @staticmethod
    def find_datatype(name) -> Tuple[str, str]:
        """Handle the syntax <class>:<gloss>.
         Returns the class and the gloss in two different strings.
         If there is no ':', returns the default 'signs' class.
         E.g.: 'gest:TJA' --> ('TJS', 'gest'); 'ABLAUF' --> ('ABLAUF', 'signs')
        """

        if ":" not in name:
            return name, "signs"
        split = name.split(":")
        return split[1], split[0]

    def handle_none(self, key) -> Optional[Tuple[float, float, float]]:
        """Retrieves the 3 values of the key + x/y/z.
          If any of them is None, returns None"""

        x = self[key + "x"]
        y = self[key + "y"]
        z = self[key + "z"]

        if not all((x, y, z)):
            return None
        
        assert x is not None
        assert y is not None
        assert z is not None

        return float(x), float(y), float(z)

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
        # TODO -- Not sure this is the best formula. If a sign duration is less than 1/FPS, frame start and frame end might be inverted!!!
        # E.g.: math.ceil(float(1.61) * 60), math.floor(float(1.616) * 60) --> (97, 96)
        return \
            math.ceil(float(self["framestart"]) * 60),\
            math.floor(float(self["frameend"]) * 60)

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
        """Number of frames from the previous gloss (in frames). Used only in relative_time mode."""
        # TODO - return the value in seconds, and defer the translation into frames
        return math.ceil(float(self["transition"]) * 60)

    def duration(self) -> Tuple[float, bool]:
        """Number of frames in the gloss.
        :returns: A 2-tuple. The first is the duration, either: i) absolute, in frames;
         or ii) as ratio of the original duration.
          The second argument is True if the duration is a ratio (case ii)."""

        # TODO - return the value in seconds, and defer the translation into frames

        duration = self["duration"]
        if "%" in duration:
            time = duration.strip("%")
            time_ratio = float(time) / 100.0
            return time_ratio, True
        return math.ceil(float(duration) * 60), False


class MMSLineDataInfo:
    """Auxiliary information to an MMSLine, holding information that can be retrieved only at run-time.
    """

    def __init__(self, mms_line: MMSLine):

        self.mms_line = mms_line

        # Filled later while scanning or loading the blend files
        self.maingloss_path: Optional[Path] = None  # Path to the Blend scene containing the gloss animation data for this MMS line.

        self.maingloss_original_frame_range: Optional[Tuple[float, float]] = None
        # TODO --  we will need to store also the framerate of the source Blenderr file, to proper resamplings among different FPS.
        # self.maingloss_original_FPS: float

        self.resampled_frame_range: Optional[Tuple[int, int]] = None

    def compose_file_paths(self, dictionary_root: Path) -> None:
        """
        Compose the gloss path and verify that the path exists.
        If the required file doesn't exist, an Exception is thrown.
        """

        maingloss_blend_file = f"{self.mms_line.name}.blend"

        self.maingloss_path = dictionary_root / self.mms_line.datatype / "trimmed" / maingloss_blend_file
        assert self.maingloss_path is not None

        if not self.maingloss_path.exists():
            raise Exception(f"Expected gloss file '{self.maingloss_path}' not present for '{self.mms_line.name}'.")


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

        # Store the availability information
        inflections_availability = {
            "domhandreloc": "domhandrelocx" in data[0],
            "ndomhandreloc": "ndomhandrelocx" in data[0],
            "domhandrot": "domhandrotx" in data[0],
            "ndomhandrot": "ndomhandrotx" in data[0],
            "torso": "torsorelocax" in data[0] and "torsorelocx" in data[0],
            "head": "headrotx" in data[0],
            "shoulders": "domshoulderrelocx" in data[0],
        }

        # Iterates on the MMS data
        rows_dict = {}
        rows_list = []
        for idx, mms_row_str in enumerate(data[1:]):
            # Convert empty values to None.
            mms_row_str = [x if x != "" else None for x in mms_row_str]
            mms_row = MMSLine(index_for_column, mms_row_str, idx)

            matches = re.findall(r'<(.*?)>', mms_row.name)

            if len(matches) > 0 and matches[0] == "HOLD":
                print(idx, "FOUND HOLD")
                # We can not handle HOLD is the first sign in the MMS.
                if idx == 0:
                    raise Exception("<HOLD> can not be used in the first row of an MMS.")

                prev_line = rows_list[idx - 1]
                # Override some mmsline properties
                mms_row.name = prev_line.name
                mms_row.datatype = prev_line.datatype
                mms_row.output_name = f"{idx}_HOLD_" + prev_line.name
                mms_row.is_hold = True

            rows_dict[(idx, mms_row.name)] = mms_row
            rows_list.append(mms_row)

        assert len(rows_dict) == len(rows_list)

        # sorts the entries according to the "framestart"
        # TODO -- actually useless if the times are given in relative mode.
        rows_ordered_dict = OrderedDict(sorted(rows_dict.items(), key=lambda x: x[1].timing()[0]))

        return MMS(rows=rows_ordered_dict, inflections_availability=inflections_availability)


# TODO -- Convert this into a test unit
if __name__ == "__main__":
    # Simple test to verify whether the parser is working or not
    parser = argparse.ArgumentParser()
    parser.add_argument("--mms-file", type=str)
    args = parser.parse_args()
    args.mms_file = os.environ["AVASAG_CORPUS_DIR"] + "/generated/mms/0009.mms"
    args.generated_root = os.environ["AVASAG_CORPUS_DIR"] + "/generated"
    parser = MMSParser(args.mms_file)
    parsed_mms = parser.parse()
    for mms_gloss in parsed_mms.row_indices:
        print("========================================")
        print(f"Using {parsed_mms[mms_gloss].output_name}")
        print("Timing: ", parsed_mms[mms_gloss].timing())
        print("Translation [ Dom]: \n", parsed_mms[mms_gloss].translation("dom"))
        print("Translation [nDom]: \n", parsed_mms[mms_gloss].translation("ndom"))

        print("Rotation [ Dom]: \n", parsed_mms[mms_gloss].traj_rotation("dom"))
        print("Rotation [nDom]: \n", parsed_mms[mms_gloss].traj_rotation("ndom"))

        print("Scale [ Dom]: \n", parsed_mms[mms_gloss].scale("dom"))
        print("Scale [nDom]: \n", parsed_mms[mms_gloss].scale("ndom"))

        print("Shoulder Shift [ Dom]: \n", parsed_mms[mms_gloss].shoulder_shift("dom"))
        print("Shoulder Shift [nDom]: \n", parsed_mms[mms_gloss].shoulder_shift("ndom"))

        print("Torso [Position]: \n", parsed_mms[mms_gloss].torso_shift())
        print("Torso [Rotation]: \n", parsed_mms[mms_gloss].torso_rot())

        print("Head [Rotation]: \n", parsed_mms[mms_gloss].head_rot())
