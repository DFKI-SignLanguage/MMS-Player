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

import bpy
import json
from pathlib import Path

from typing import List

def format_bone_quaternion(rotation) -> dict:
    w = str(rotation.w)
    x = str(rotation.x)
    y = str(rotation.y)
    z = str(rotation.z)
    return {
        "boneRotation": [
            "0" if "e" in w else w,
            "0" if "e" in x else x,
            "0" if "e" in y else y,
            "0" if "e" in z else z,
        ]
    }


def export_animation(armature_obj: bpy.types.Object, bones_list: List[str], out_json_path: Path) -> None:
    """Exports the animation of the currently activa action of the given armature into a custom JSON format.
    Only data of the bones specified in the bones_list is exported"""

    # Get the current playback FPS from the Blender bpy.context
    playback_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base

    frame_start = int(armature_obj.animation_data.action.frame_range[0])
    frame_end = int(armature_obj.animation_data.action.frame_range[1])
    frame_count = frame_end - frame_start + 1

    finalJson = {
        "bones": bones_list,
        "playback_fps": str(playback_fps),
        "frame_count": frame_count,
        "animData": [],
    }


    for f in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(f)
        newRotations = {"rotationsDatas": []}
        for pbone_name in bones_list:
            pbone = armature_obj.pose.bones[pbone_name]
            quaternion = pbone.rotation_euler.to_quaternion()
            newRotations["rotationsDatas"].append(format_bone_quaternion(quaternion))
        finalJson["animData"].append(newRotations)

    with open(out_json_path, "w") as jsonfile:
        json.dump(obj=finalJson, fp=jsonfile, indent=4)
