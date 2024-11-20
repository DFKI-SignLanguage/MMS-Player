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
from pathlib import Path
import json


ACTIVE_BONES_WITH_FINGERS = [
    "Bone_Root",
    "Bone",
    "Bone_Pelvis",
    "Bone_Spine",
    "Bone_Spine1",
    "Bone_Spine2",
    "Bone_Neck",
    "Bone_Head",
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


ACTIVE_BONES_WITHOUT_FINGERS = [
    "Bone_Root",
    "Bone",
    "Bone_Neck",
    "Bone_Head",
    "Bone_Pelvis",
    "Bone_Spine",
    "Bone_Spine1",
    "Bone_Spine2",
    "Bone_L_Clavicle",
    "Bone_L_UpperArm",
    "Bone_L_Forearm",
    "Bone_L_Hand",
    "Bone_R_Clavicle",
    "Bone_R_UpperArm",
    "Bone_R_Forearm",
    "Bone_R_Hand",
]
# In order to make sure the frame number matches the target frame number,
# I need to sample the values.

# A simple example to verify this extraction:
# 1. Create a simple armature with 3 bones.
# 2. Create a simple animation with 5 frames.
# 3. Interpolate the animation frames to 10 frames.
# 4. Now create a new action
#   a. duplicate and delete all the keyframes in the new action.
#   b. Sample a keyframe and get the interpolated value at "t" value.
#   c. Once insert the t value into the key frame.
#   d. Repeat this for all 10 frames.
# 5. Bake the new action into the armature and delete the old animation.
# 6. This function will be called as interpolate function.
# 7. This might still incur issues from the original animation because of the interpolation.
# 8. Measure the error for the interpolated animation.


def set_rotation_and_location(source_action, source_bone_name, source_frame, target_action, target_frame):

    rot_path_name = f'pose.bones["{source_bone_name}"].rotation_euler'
    for i in range(3):
        fcurve = source_action.fcurves.find(rot_path_name, index=i)
        sampled_value = fcurve.evaluate(source_frame)
        target_fcurve = target_action.fcurves.find(rot_path_name, index=i)
        target_fcurve.keyframe_points.insert(target_frame, sampled_value)

    loc_path_name = f'pose.bones["{source_bone_name}"].location'
    for i in range(3):
        fcurve = source_action.fcurves.find(loc_path_name, index=i)
        sampled_value = fcurve.evaluate(source_frame)
        target_fcurve = target_action.fcurves.find(loc_path_name, index=i)
        target_fcurve.keyframe_points.insert(target_frame, sampled_value)


def extract_target(target_armature, gloss, start, end, active_bones):
    print(f"Using {start} and {end} to extract the data.")
    bpy.ops.object.mode_set(mode="POSE")
    bone_data = {
        "gloss_name": gloss.output_name,
        "rotation": [],
        "translation": [],
        "rotation_euler": [],
    }

    for frame in range(start, end):
        bpy.context.scene.frame_set(frame)
        translation_data = {}
        rotation_data = {}
        rotation_euler_data = {}
        for bone in target_armature.pose.bones:
            if bone.name not in active_bones:
                continue
            translation, rotation, _ = bone.matrix.decompose()
            rotation_euler = rotation.to_euler()

            rotation_data[bone.name] = [rotation.x, rotation.y, rotation.z, rotation.w]
            rotation_euler_data[bone.name] = [
                rotation_euler.x,
                rotation_euler.y,
                rotation_euler.z,
            ]
            translation_data[bone.name] = [translation.x, translation.y, translation.z]
            # print(bone.name, translation, ACTIVE_BONES.index(bone.name))
        bone_data["rotation"].append(rotation_data)
        bone_data["rotation_euler"].append(rotation_euler_data)
        bone_data["translation"].append(translation_data)

    bpy.ops.object.mode_set(mode="OBJECT")
    return bone_data


def create_f_curves(source_armature: bpy.types.Armature, sampled_action: bpy.types.Action):
    """For each bone of the given armature,
     creates rotation_euler/ location f-curves on the given action (if not present, yet).
    Useful to prepare an action to receive full skeleton animation data."""

    for bone in source_armature.pose.bones:
        name = bone.name
        for i in range(3):
            path_name = f'pose.bones["{name}"].rotation_euler'
            fcurve = sampled_action.fcurves.find(path_name, index=i)
            if not fcurve:
                sampled_action.fcurves.new(data_path=path_name, index=i)
            path_name = f'pose.bones["{name}"].location'
            fcurve = sampled_action.fcurves.find(path_name, index=i)
            if not fcurve:
                sampled_action.fcurves.new(data_path=path_name, index=i)


def extract_source(source_armature, gloss, sample_size):
    # Get a sample action, if it doesn't exist, create it
    sampled_action = bpy.data.actions.get(f"sampled_{gloss.output_name}")
    if sampled_action is None:
        sampled_action = bpy.data.actions.new(name=f"sampled_{gloss.output_name}")

    # Create fcurves for each bone rotation
    create_f_curves(source_armature=source_armature, sampled_action=sampled_action)
    action = source_armature.animation_data.action
    frame_start = int(action.frame_range[0])
    frame_end = int(action.frame_range[1])
    ratio = (frame_end - frame_start) / (sample_size - 1)
    samples = [frame_start + x * ratio for x in range(sample_size)]
    for frame_number, sample in enumerate(samples):
        for bone in source_armature.pose.bones:
            if "IK" in bone.name:
                continue
            set_rotation_and_location(source_action=action, source_bone_name=bone.name, source_frame=sample,
                                      target_action=sampled_action, target_frame=frame_number + 1)
    source_armature.animation_data.action = sampled_action
    return extract_target(source_armature, gloss, 1, len(samples) + 1)


def extract_normal(mms, trim_start, skeleton, active_bones):
    final_data = {}
    for gloss in mms.glosses:
        mms_line = mms[gloss]
        print("Extracting data for: ", mms_line.name)
        start, end = mms_line.timing()
        start = start - (trim_start)
        start = start if start != 0 else 1
        end = end - (trim_start)
        #         assert mms_line.data is not None, "MMS data is not present"
        target_data = extract_target(skeleton, mms_line, start, end + 1, active_bones)

        source_name = f"inflected_{mms_line.output_name}"
        assert source_name is not None, "Inflected armature is not present."

        source_armature = bpy.data.objects[source_name]
        source_data = extract_target(
            source_armature, mms_line, 1, end - start + 2, active_bones
        )
        source_len = len(source_data["rotation"]) // (4 * len(active_bones))
        target_len = len(target_data["rotation"]) // (4 * len(active_bones))
        assert source_len == target_len, "Sanity check for assuring same sample size."
        final_data[mms_line.output_name] = {
            "num_frame": target_len,
            "source": source_data,
            "target": target_data,
        }
    return final_data


def extract_custom(mms, active_bones):
    final_data = {}
    for gloss in mms.glosses:
        mms_line = mms[gloss]
        # If the sign animation doesn't exist, increase the start range.

        target = bpy.data.objects[gloss[1]]
        start, end = target.animation_data.action.frame_range
        target_data = extract_target(
            target, mms_line, int(start), int(end) + 1, active_bones
        )

        source = bpy.data.objects[f"inflected_{gloss[0]}_{gloss[1]}"]
        source_data = extract_target(source, mms_line, 1, end - start + 2, active_bones)
        target_len = len(target_data["rotation"]) // (4 * len(active_bones))

        final_data[mms_line.output_name] = {
            "num_frame": target_len,
            "source": source_data,
            "target": target_data,
        }
    return final_data


def run(
    mms,
    sentence_id,
    generated_dir,
    output_path=None,
    use_rel_time=False,
    without_fingers=False,
):
    """Run the full data extraction for evaluation.

    Since everything is loaded into a single blend file, the data extraction process is
    trival.

    We have to sample the actions, extract the required position and rotation data.
    Note: target = sentence; source = original gloss

    1. First we import the sentence animation

        a. Get the timing of each gloss data
        b. Using this timing data, we extract corresponding data from the sentence
        c. Use the length to sample the animation from the original gloss animation
        d. Finally, extract gloss data from the sampled points
    """
    id = "Satz" + sentence_id.lstrip("0")

    trim_info = Path(generated_dir).parent.joinpath(
        "mocapdata", "sentences", f"{id}.triminfo"
    )

    if output_path is None:
        output_path = Path(generated_dir).joinpath(
            "inflections", sentence_id, "evaluation_data.json"
        )

    animation_data = Path(generated_dir).joinpath("sentences", "trimmed", f"{id}.blend")

    sentence_data = None
    active_bones = ACTIVE_BONES_WITH_FINGERS
    if without_fingers:
        active_bones = ACTIVE_BONES_WITHOUT_FINGERS

    if use_rel_time:
        output_path = Path(f"./test/")
        final_data = extract_custom(mms, active_bones)
    else:
        with bpy.data.libraries.load(str(animation_data)) as (data_from, data_to):
            data_to.objects = data_from.objects
            sentence_data = data_to

        skeleton = sentence_data.objects[0]
        bpy.context.scene.collection.objects.link(skeleton)
        assert sentence_data.objects[0] != None, "Sentence is loaded."
        # print([(i, obj.name) for (i, obj) in enumerate(sentence_data.objects)])
        # print("Sentence name: ", sentence_data.objects[0].name)

        assert trim_info.exists(), f"The offset file doesn't exist.\nPath: {trim_info}"
        with open(trim_info, "r") as fp:
            data = fp.readline().strip("\n").split(" ")
        trim_start = int(data[0]) - 1
        print(f"The start of animation is: {trim_start}")

        final_data = extract_normal(mms, trim_start, skeleton, active_bones)

    with open(output_path, "w") as stream:
        json.dump(final_data, stream, indent=2)
