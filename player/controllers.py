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
# Orchestration of the IK controller.
#
#
# There are a lot of IK bones for realization of the bone inflections.
# Next, it is necessary to evaluate the order of the application of the IK bones.
#
# With each IK motions, different bones are going to be affected. This module contains
# the necessary IK controllers for the skeleton.
#
# It has to do the following things:
# 1. Store the reference to parent of the IK bone.
# 2. Create an IK bone
# 3. Store the forward motion of the IK bone.
# 4. Bake it into IK.
# 5. Apply the IK inflection on the IK bones.
#

import bpy
from typing import List

from . import targets
from . import bpy_utils
from .logging import logger
from .mms_parser import MMSLine


class Controller:
    """Responsible for orchestrating the IK controller."""
    def __init__(self,
                 armature: bpy.types.Armature,
                 dictionary_armature_name: str,
                 ik_targets: List[targets.IKTargetConfig],
                 idx: int) -> None:
        """Initialize Controller object.

        @param armature: The source armature to be inflected.
        @param dictionary_armature_name: The name of the armature in dictionary.
        @param ik_targets: The list of IK targets responsible for controlling the bones.
        @param idx: The identifier for the gloss.
        """
        self.ik_targets = []
        # Dynamically compose the inflection targets that allow to perform the inflection.
        for target_data in ik_targets:
            obj_class = getattr(targets, target_data.target)
            ik_target = obj_class(
                idx,
                armature=armature,
                dictionary_name=dictionary_armature_name,
                dominance=target_data.dominance,
                target_bone=target_data.bone,
                target_root=target_data.root,
                inflection_type=target_data.itype,
                constraints=target_data.constraints,
            )
            self.ik_targets.append(ik_target)

    def setup_chain(self,
                    source_armature: bpy.types.Armature,
                    target_armature: bpy.types.Armature,
                    output_name: str,
                    mms_line: MMSLine,
                    without_inflection: bool = False):
        """Set up the armature skeleton for animation.

        @param source_armature: The source armature containing the signing animation
        @param target_armature: The target armature that contains the IK controller.
        @param output_name: The name of the inflected action.
        @param mms_line: The row of the corresponding gloss.
        @param without_inflection: This flag allows to disable the animation.

        Note:
            1. We copy the original animation from the source into the target.
            This redundancy prevents us from modifying the original animation.

            2. Once we copy the animation, we update the animation of corresponding
            IK controllers.
        """
        source_action = source_armature.animation_data.action
        start = int(source_action.frame_range[0])
        end = int(source_action.frame_range[1])
        # print(f"Source animation {action.name} range: {start} to {end}")
        # 1. Copy skeletal animation from the main action track to the "inflected" one
        bpy_utils.select_object(target_armature)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.select_all(action="SELECT")
        new_action = bpy.data.actions.get(f"inflected_{output_name}")
        target_armature.animation_data.action = new_action
        bpy.context.object.animation_data.action = new_action
        bpy.context.scene.frame_set(start)
        # print("Baking the forward pose into the IK bones.")
        # This handles the off-by-1 error!
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            for bone in source_armature.pose.bones:
                tgt_bone = target_armature.pose.bones[bone.name]
                tgt_bone.matrix_basis = bone.matrix_basis.copy()
                tgt_bone.keyframe_insert("location", frame=frame)
                tgt_bone.keyframe_insert("rotation_euler", frame=frame)

        # This performs the "baking" of the animation into the given animation IK controller
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            for obj in self.ik_targets:
                tgt_bone = target_armature.pose.bones[obj.target_bone]
                tgt_root = target_armature.pose.bones[obj.target_root]
                location = tgt_bone.head + (tgt_root.head - tgt_root.tail)
                rotation = tgt_bone.rotation_euler.to_quaternion()
                if not isinstance(obj, targets.TrajectoryTarget):
                    continue
                elif isinstance(obj, targets.RelativeLocRotTarget):
                    location = tgt_bone.tail + (tgt_root.head - tgt_root.tail)
                elif isinstance(obj, targets.HeadRotTarget):
                    location = tgt_bone.tail + (tgt_root.head - tgt_root.tail)
                    rotation = (
                        tgt_root.matrix.to_quaternion().inverted()
                        @ tgt_bone.matrix.to_quaternion()
                    )
                obj.ctrl.location = tgt_root.matrix.inverted() @ location
                obj.ctrl.rotation_quaternion = rotation
                obj.ctrl.keyframe_insert("location", frame=frame)
                obj.ctrl.keyframe_insert("rotation_quaternion", frame=frame)

        bpy.ops.object.mode_set(mode="OBJECT")
        for bone in self.ik_targets:
            bone.add_constraints()
            if not without_inflection:
                bone.init_from_mms(mms_line)
        # TODO: When without inflection, avoid the baking and copying animation.
        #       Instead use the original animation. (Priority: Low)

    def execute(self, armature: bpy.types.Armature, mms_line: MMSLine):
        """Inflect the IK targets and bake the animation.

        @param armature: The target armature containing the IK targets.
        @param mms_line: The MMS table
        """

        bpy_utils.select_object(armature)
        bpy.ops.object.mode_set(mode="POSE")
        action = bpy.data.actions.get(f"inflected_{mms_line.output_name}")
        bpy.context.object.animation_data.action = action
        start = int(action.frame_range[0])
        stop = int(action.frame_range[1])
        logger.info(f"Frame start: {start}, Frame End: {stop}")

        # Inflect each of the targets per frame.
        for frame in range(start, stop + 1):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bone in self.ik_targets:
                bone.inflect(frame)
            # break
        # return

        # Finally bake the animation
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.nla.bake(
            frame_start=start,
            frame_end=stop,
            step=1,
            only_selected=True,
            visual_keying=True,
            clear_constraints=False,
            use_current_action=True,
            bake_types={"POSE"},
        )
        bpy.ops.object.mode_set(mode="OBJECT")
