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
import sys
import json
import argparse

ACTIVE_BONES = [
    "Bone_Root",
    "Bone",
    "Bone_Pelvis",
    "Bone_Spine",
    "Bone_Spine1",
    "Bone_Spine2",
    "Bone_L_Clavicle",
    "Bone_L_UpperArm",
    "Bone_L_Forearm",
    "Bone_L_Hand",
    "Bone_L_Finger0",
    "Bone_L_Finger01",
    "Bone_L_Finger02",
    "Bone_L_Finger1",
    "Bone_L_Finger11",
    "Bone_L_Finger12",
    "Bone_L_Finger13",
    "Bone_L_Finger2",
    "Bone_L_Finger21",
    "Bone_L_Finger22",
    "Bone_L_Finger23",
    "Bone_L_Finger3",
    "Bone_L_Finger31",
    "Bone_L_Finger32",
    "Bone_L_Finger33",
    "Bone_L_Finger4",
    "Bone_L_Finger41",
    "Bone_L_Finger42",
    "Bone_L_Finger43",
    "Bone_R_Clavicle",
    "Bone_R_UpperArm",
    "Bone_R_Forearm",
    "Bone_R_Hand",
    "Bone_R_Finger0",
    "Bone_R_Finger01",
    "Bone_R_Finger02",
    "Bone_R_Finger1",
    "Bone_R_Finger11",
    "Bone_R_Finger12",
    "Bone_R_Finger13",
    "Bone_R_Finger2",
    "Bone_R_Finger21",
    "Bone_R_Finger22",
    "Bone_R_Finger23",
    "Bone_R_Finger3",
    "Bone_R_Finger31",
    "Bone_R_Finger32",
    "Bone_R_Finger33",
    "Bone_R_Finger4",
    "Bone_R_Finger41",
    "Bone_R_Finger42",
    "Bone_R_Finger43",
]


def fetch_bone_quaternion(rotation):
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


def get_animation_list(active_bones, fbx_path=None, blend_path=None, json_path=None):
    if fbx_path:
        bpy.ops.import_scene.fbx(filepath=fbx_path)

    if blend_path:
        bpy.ops.wm.open_mainfile(filepath=blend_path)

    sampling_rate = 1 / 60
    finalJson = {
        "bones": active_bones,
        "samplingRate": str(sampling_rate),
        "animData": [],
    }
    armature = bpy.data.objects["skeleton #5"]
    frame_start = int(armature.animation_data.action.frame_range[0])
    frame_end = int(armature.animation_data.action.frame_range[1])

    for f in range(frame_start, frame_end):
        bpy.context.scene.frame_set(f)
        newRotations = {"rotationsDatas": []}
        for pbone_name in active_bones:
            pbone = armature.pose.bones[pbone_name]
            quaternion = pbone.rotation_euler.to_quaternion()
            newRotations["rotationsDatas"].append(fetch_bone_quaternion(quaternion))
        finalJson["animData"].append(newRotations)

    with open(json_path, "w") as jsonfile:
        jsonfile.writelines(json.dumps(finalJson))


if __name__ == "__main__":
    argv = sys.argv

    if "--" not in argv:
        argv = []  # as if no args are passed
    else:
        argv = argv[argv.index("--") + 1 :]  # get all args after "--"

    parser = argparse.ArgumentParser()
    parser.add_argument("--fbx-path", help="Path to the fbx data", type=str)
    parser.add_argument("--blend-path", help="Path to the blend data", type=str)
    parser.add_argument("--json-path", help="Path to the JSON data", type=str)
    args = parser.parse_args(argv)
    get_animation_list(ACTIVE_BONES, args.fbx_path, args.blend_path, args.json_path)
