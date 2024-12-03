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
from copy import deepcopy
from pathlib import Path
from typing import Optional, Tuple, Dict, List


class MMSLine:
    """MMSLine represents a single row of the MMS table.
    
    Since each row in the table associates to a different sign necessary to 
    be inflected, the class functions to store and retrieve the data required
    for the inflection of the corresponding sign.
    """
    def __init__(self, store_index: Dict[str, int], line_data: list, gloss_idx: int):
        self.store_index = store_index  # Maps the column name to its index within the MMS row
        self.line_data = line_data
        self.name, self.datatype = self.find_datatype(line_data[0])
        self.output_name = f"{gloss_idx}_{self.name}"  # We overwrite the name.
        self.path = Path("/none")
        self.data = None
        self.original_frame_range = None
        self.resampled_frame_range = None

    def __getitem__(self, key):
        return self.line_data[self.store_index[key]]

    def __repr__(self):
        return f"(MMSLine for {self.name} {self.datatype})"

    def keys(self):
        return list(self.store_index.keys())

    @staticmethod
    def find_datatype(name) -> Tuple[str, str]:
        """Find the associated gloss type.
        
        The gloss database has different types. This information is essential
        when access the animation from the gloss database.
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
        """Start and the end frame in the as in the original sentence."""
        # TODO -- Not sure this is the best formula. If a sign duration is less than 1/FPS, frame start and frame end might be inverted!!!
        # E.g.: math.ceil(float(1.61) * 60), math.floor(float(1.616) * 60) --> (97, 96)
        return math.ceil(float(self["framestart"]) * 60), math.floor(
            float(self["frameend"]) * 60
        )

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


class MMS:
    """MMS table representation.
    
    Attributes:
        mms: the MMS table which is an ordered dict of items sorted according to time
        glosses: A list of consisting of row id and corresponding gloss_id.
        inflections_availability_dict: Contains the information if given mms data is present or not.
    """

    def __init__(self,
                 mms: Dict[Tuple[int, str], MMSLine],
                 generated_root: Path,
                 inflections_availability: Dict[str, bool] = None):

        self.mms: Dict[Tuple[int, str], MMSLine] = mms
        self.glosses: List[Tuple[int, str]] = list(mms.keys())
        self.generated_root: Path = generated_root
        self.inflections_availability_dict: Dict[str, bool] = inflections_availability

    def __getitem__(self, key: Tuple[int, str]) -> MMSLine:
        """Access the MMS line using the given key."""
        if key not in self.mms:
            raise KeyError(f"{key} not found in the mms")
        return self.mms[key]

    def __repr__(self):
        return f"MMS({self.glosses})"

    def find_mocap_data_files(self) -> None:
        """Save the path information for each gloss in the MMS table.

        As we assign the gloss path, we verify that the path exists.
        """
        pattern = r'<(.*?)>'
        for num, gloss_id in enumerate(self.glosses):
            gloss = self[gloss_id]
            matches = re.findall(pattern, gloss.name)
            if len(matches) > 0 and matches[0] == "HOLD":
                # TODO -- Why the path is set to the path of the previous gloss? And if the HOLD is the first sign in the MMS?
                self[gloss_id].path = self[self.glosses[num - 1]].path
                self[gloss_id].datatype = "HOLD"
            else:
                motion_file = f"{gloss.name}.blend"
                gloss_path = (
                    Path(self.generated_root)
                    .joinpath(gloss.datatype)
                    .joinpath("trimmed")
                    .joinpath(motion_file)
                )

                if not gloss_path.exists():
                    raise Exception(f"Expected motion capture file '{gloss_path}' not present for {gloss.name}.")

            self[gloss_id].path = gloss_path


class MMSParser:
    """The parser for MMS data."""
    def __init__(self, mms_file, generated_root):
        self.mms_file = Path(mms_file)
        self.generated_root = Path(generated_root)

    def parse(self):
        """Parse the mms file and return the MMS object.
        
        In order to parse the data:
        1. Read the CSV file consisting the MMS data.
        2.
        """
        with open(self.mms_file, "r") as read_stream:
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
        glosses = {}
        idx = 0
        for gloss_line in data[1:]:
            name, prefix = MMSLine.find_datatype(gloss_line[0])
            # Convert empty values to None.
            gloss_line = [x if x != "" else None for x in gloss_line]

            # Handle the glosses with dashes such as: R-E:1-5-9-7
            if prefix != "signs" and "-" in name:
                start = float(gloss_line[index_for_column["framestart"]])
                end = float(gloss_line[index_for_column["frameend"]])
                diff = end - start
                names = name.split("-")
                delta = diff / len(names)
                scale = 0.3
                for i, gloss in enumerate(names):
                    line = deepcopy(gloss_line)
                    line[0] = prefix + ":" + gloss
                    line[index_for_column["framestart"]] = start + delta * i
                    line[index_for_column["frameend"]] = (
                        start + delta * (i + 1) - scale * delta
                    )
                    line[index_for_column["transition"]] = scale * delta
                    # Add the final transition information.
                    if i == len(names) - 1:
                        line[index_for_column["transition"]] = gloss_line[
                            index_for_column["transition"]
                        ]
                    # Create a new gloss MMS line for the given fragment.
                    gloss_data = MMSLine(index_for_column, line, idx + i)
                    glosses[(idx + i, gloss_data.name)] = gloss_data
                idx += len(names)
                continue        # <-- BEWARE! Jumps out of the cycle, to the next row.

            gloss_data = MMSLine(index_for_column, gloss_line, idx)
            glosses[(idx, gloss_data.name)] = gloss_data
            idx += 1

        # sorts the entries according to the "framestart"
        # TODO -- actually useless if the times are given in relative mode.
        glosses = OrderedDict(sorted(glosses.items(), key=lambda x: x[1].timing()[0]))

        return MMS(mms=glosses, generated_root=self.generated_root, inflections_availability=inflections_availability)


# TODO -- Convert this into a test unit
if __name__ == "__main__":
    # Simple test to verify whether the parser is working or not
    parser = argparse.ArgumentParser()
    parser.add_argument("--mms-file", type=str)
    parser.add_argument("--generated-root", type=str)
    args = parser.parse_args()
    args.mms_file = os.environ["AVASAG_CORPUS_DIR"] + "/generated/mms/0009.mms"
    args.generated_root = os.environ["AVASAG_CORPUS_DIR"] + "/generated"
    parser = MMSParser(args.mms_file, args.generated_root)
    parsed_mms = parser.parse()
    for mms_gloss in parsed_mms.glosses:
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
