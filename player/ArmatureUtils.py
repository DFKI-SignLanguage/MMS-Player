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
# Bakes the inflections into the library gloss.
#

import math
import bpy
from pathlib import Path
from typing import Tuple, Union, Optional

from .logging import logger
from .mms_parser import MMSLine
from . import bpy_utils, extract


class ArmatureOperator:
    """ArmatureOperator is responsible for baking the inflected gloss animation.

    It has to fulfill the following criteria:
    1. Load the gloss animation.
    2. Add an IK controller on this animation bone.
    3. Create a copy of the armature
    4. Copy the trajectory of the animation.
    5. Finally, apply the animation.
    """

    def __init__(self, mms_line: MMSLine) -> None:

        self.mms_line = mms_line
        self.src_armature: Optional[bpy.types.Object] = None

    def load_animation(self) -> None:
        """Load the animation into the scene.

        This code copies the assets from the library and links it into the current blender
        context. Since the context data can be overwritten, we store a link in mms line.
        """

        blend_path = self.mms_line.path

        logger.info(f"Loading GLOSS animation data from '{blend_path}' ...")

        if not blend_path.exists():
            raise Exception(f"Failed to find the library data '{str(blend_path)}'.")

        with bpy.data.libraries.load(str(blend_path)) as (data_from, data_to):
            data_to.objects = data_from.objects
            data_to.armatures = data_from.armatures
            data_to.actions = data_from.actions
            self.mms_line.bpy_data = data_to  # Store in the mms line a reference to the the bpy.data containing objetcs, aramtures and actions of the current context, loaded from the animation blend file.

        #
        # Find the armature and import it with the associated armature action
        #

        # Have to cycle through the objects, because they are not a dictionary, but a list (blender type bpy_lib !)
        armature_obj: Optional[bpy.types.Object] = None
        for o in self.mms_line.bpy_data.objects:
            if o.type == 'ARMATURE':
                if self.mms_line.name == "<HOLD>":
                    logger.info(f"While loading the animation for <HOLD> gloss {self.mms_line.output_name}, using the first found armature '{o.name}'. We are not checking if the armature name is the same as in the previous gloss.")
                    armature_obj = o
                    break
                # print(">>>", type(o), o.name, o.type)
                elif o.name == self.mms_line.name:
                    armature_obj = o
                    break

        if armature_obj is None:
            raise Exception(f"ARMATURE Object with name {self.mms_line.name} not found while loading animation for {self.mms_line.output_name}")

        assert armature_obj.type == 'ARMATURE', f"Expected type ARMATURE for {armature_obj.name}: found '{armature_obj.type}' instead"

        # Link the source armature to the current context
        bpy.context.scene.collection.objects.link(armature_obj)

        # Replacing the armature name with the one including the progress number
        armature_obj.name = self.mms_line.output_name
        # Set the name of the imported action, avoiding duplicates and auto renaming in case of multiple glosses with the same name in the MMS
        armature_obj.animation_data.action.name = "imported_" + self.mms_line.output_name

        logger.info(f"Initialized armature '{armature_obj.name}' with action '{armature_obj.animation_data.action.name}'")

        #
        # Check for the presence of the Blendshape face animation
        face_action_name = "blendshapes_" + self.mms_line.name
        if self.mms_line.name != "<HOLD>" and face_action_name not in bpy.data.actions:
            raise Exception(f"Face animation '{face_action_name}' not found in loaded scene.")

        # Rename the action to a unique name
        face_action = bpy.data.actions[face_action_name]
        face_action.name = "imported_blendshapes_" + self.mms_line.output_name

        self.src_armature = armature_obj

    def resample(self, timing: Union[Tuple[float, float], Tuple[float, bool]], target_action_name: str, use_rel_time: bool):
        """Resample the animation according to the timing information.
        We assume that the animation has been loaded in the current armature's action.
        This function will create a new action with the resampled duration and set it as current action.

        :param timing: If use_rel_time is False, the timing is a tuple containing the MMS (framestart, frameend)
         already converted in frame position.
          If use_rel_time if True, the timing is a tuple (duration, pct),
           where the duration can be expressed as absolute vale in frames, or as a percentage of the original duration.
        :param use_rel_time: whether to use relative timing, or not.
        """

        # 1. Initialize the armature and create a new action.
        source_armature = self.src_armature

        self.mms_line.original_frame_range = source_armature.animation_data.action.frame_range[0], source_armature.animation_data.action.frame_range[1]

        sampled_action = bpy.data.actions.new(name=target_action_name)

        # Compute the resampling time
        # TODO -- bring this out and let the duration of a resampling be calculated in the MMSLine class
        if not use_rel_time:
            start, end = timing
            target_frame_count = end - start + 1
        else:
            duration_or_prop, is_proportion = timing
            if is_proportion:
                action = source_armature.animation_data.action
                frame_start = int(action.frame_range[0])
                frame_end = int(action.frame_range[1])
                target_frame_count = math.ceil(duration_or_prop * (frame_end - frame_start) + 1)
            else:
                target_frame_count = duration_or_prop

        # 2. Iterate through the bones and create a new f-curve if it doesn't exist.
        extract.create_f_curves(source_armature=source_armature, sampled_action=sampled_action)

        # 3. Resample the animation using sampling ratio and write the rotations.
        action = source_armature.animation_data.action
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        ratio = (frame_end - frame_start) / (target_frame_count - 1)
        samples = [frame_start + x * ratio for x in range(target_frame_count)]

        for frame_number, sample in enumerate(samples):
            for bone in source_armature.pose.bones:
                extract.set_rotation_and_location(
                    source_action=action, source_bone_name=bone.name, source_frame=sample,
                    target_action=sampled_action, target_frame=frame_number + 1
                )

        source_armature.animation_data.action = sampled_action

        self.mms_line.resampled_frame_range = source_armature.animation_data.action.frame_range[0], source_armature.animation_data.action.frame_range[1]

    def resample_blendshapes_action(self, timing: Union[Tuple[float, float], Tuple[float, bool]], use_rel_time: bool, src_action_name: str, target_action_name: str) -> None:
        """Resample the given source action into a new action with the given target name.
        :param timing:  If use_rel_time is False, the timing is a tuple containing the MMS (framestart, frameend)
         already converted in frame position.
          If use_rel_time if True, the timing is a tuple (duration, pct),
           where the duration can be expressed as absolute vale in frames, or as a percentage of the original duration.
        :param use_rel_time: whether to use relative timing, or not.
        :param src_ation_name: The name of the existing action
        :param target_action_name: The name of the action to be created
        """

        src_action = bpy.data.actions[src_action_name]

        # Compute target_frame_count — same logic as resample()
        if not use_rel_time:
            start, end = timing
            target_frame_count = end - start + 1
        else:
            duration_or_prop, is_proportion = timing
            if is_proportion:
                frame_start = int(src_action.frame_range[0])
                frame_end = int(src_action.frame_range[1])
                target_frame_count = math.ceil(duration_or_prop * (frame_end - frame_start) + 1)
            else:
                target_frame_count = duration_or_prop

        sampled_action = bpy.data.actions.new(name=target_action_name)

        # Mirror every fcurve from the source into the new action
        for src_fcurve in src_action.fcurves:
            sampled_action.fcurves.new(data_path=src_fcurve.data_path, index=src_fcurve.array_index)

        # Build sample points spanning the source frame range
        frame_start = int(src_action.frame_range[0])
        frame_end = int(src_action.frame_range[1])
        target_frame_count = int(target_frame_count)
        ratio = (frame_end - frame_start) / (target_frame_count - 1)
        samples = [frame_start + x * ratio for x in range(target_frame_count)]

        for frame_number, sample in enumerate(samples):
            for src_fcurve in src_action.fcurves:
                sampled_value = src_fcurve.evaluate(sample)
                target_fcurve = sampled_action.fcurves.find(src_fcurve.data_path, index=src_fcurve.array_index)
                target_fcurve.keyframe_points.insert(frame_number + 1, sampled_value)

        assert target_action_name in bpy.data.actions


    def copy_armature(self) -> bpy.types.Object:
        """Creates a copy of the armature and its animation.
        :return: the reference to the armature copy.
        """
        bpy_utils.select_object(self.src_armature)

        if self.src_armature is None:
            raise Exception("Can't copy the armature. Source is None")

        duplicate_armature = bpy_utils.duplicate(
            self.src_armature, self.mms_line.output_name
        )
        bpy.context.view_layer.update()
        return duplicate_armature
