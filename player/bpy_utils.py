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
# Utility class to help blender operations.
#

import bpy
import mathutils
import tempfile
from pathlib import Path

from mathutils import Vector


def select_object(bpy_object):
    """Select the object"""
    # It is import to verify which mode we are in. This will help us clean
    # the code. It will also makes sure that we communicate the what is
    # actually happening here.
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = bpy_object
    bpy_object.select_set(True)


def get_trajectory(armature, bone_name):
    """Get the trajectory of the bone.

    It assumes that the action is already trimmed after being
    parsed by the MMSParser.
    """

    select_object(armature)
    # bpy.ops.object.mode_set(mode="POSE")
    actions = bpy.context.object.animation_data.action
    start_frame = int(actions.frame_range[0])
    end_frame = int(actions.frame_range[1])
    data = []
    bone_pose = armature.pose.bones[bone_name]
    for frame in range(start_frame, end_frame):
        bpy.context.scene.frame_set(frame)
        data.append(bone_pose.head.copy())
    return data


def select_bone(bone):
    bone.select = True
    bone.select_head = True
    bone.select_tail = True


def duplicate(src_armature, name):
    duplicate_armature = src_armature.copy()
    duplicate_armature.data = src_armature.data.copy()
    duplicate_armature.animation_data_clear()
    duplicate_armature.animation_data_create()
    bpy.context.collection.objects.link(duplicate_armature)

    select_object(duplicate_armature)
    bpy.context.object.name = f"inflected_{name}"
    bpy.context.object.data.name = f"inflected_{name}"
    new_action = bpy.data.actions.new(name=f"inflected_{name}")
    bpy.context.object.animation_data.action = new_action
    return duplicate_armature


def add_copy_constraints(armature, name: str, subtarget: str):
    controller = armature.pose.bones[name]
    constraint = controller.constraints.new("COPY_TRANSFORMS")
    constraint.name = name
    constraint.subtarget = subtarget
    constraint.target = armature


def add_ik_bone(armature, parent_name) -> str:
    """Add an IK bone to the armature.
    Args:
        armature_name: The name of the armature.
        bone_name: The name of the bone.
        scale: The scale of new ik controller.
    """
    if bpy.context.mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    new_bone = armature.data.edit_bones.new(f"IK_for_{parent_name}")
    new_bone.parent = None
    new_bone.head = mathutils.Vector((0, 0, 0))
    new_bone.tail = mathutils.Vector((0, 0.5, 0))
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="POSE")
    ik_bone = armature.pose.bones[f"IK_for_{parent_name}"]
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    return ik_bone.name


def remove_ik_bone(target, ik_bone: str):
    if ik_bone == "Bone":
        return
    select_object(target)
    if bpy.context.mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.armature.select_all(action="DESELECT")
    ik_bone = target.data.edit_bones[ik_bone]
    target.data.edit_bones.remove(ik_bone)
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")


def add_ik_constraint(armature, target, subtarget):
    print(armature.name, target, subtarget)
    target_bone = armature.pose.bones[target]
    ik_constraint = target_bone.constraints.new("IK")
    ik_constraint.target = armature
    ik_constraint.subtarget = subtarget
    ik_constraint.chain_count = 4
    ik_constraint.use_rotation = False
    ik_constraint.use_tail = False
    bpy.context.view_layer.update()


def modify_animation(bvh_path, name):
    """Fix the zero length bones in the animation data.

    It finds the `OFFSET 0 0 0` and updates the position for each of the bones.
    """
    with open(bvh_path, "r") as read_stream:
        data = read_stream.readlines()
        read_stream.close()

    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="updated_", suffix=f"_{name}.bvh", delete=False
    )
    for i, each in enumerate(data):
        if "OFFSET 0 0 0" in each:
            data[i] = each.replace("T 0 0 0", "T 0.1 0.0 0.0")
        if "MOTION" in each:
            break
    tmp_file.writelines(data)
    tmp_file.close()
    return tmp_file.name, Path(tmp_file.name).stem
