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
from typing import Tuple, Union

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
        self.src_armature = self.load_animation(mms_line.path)
        assert Path(mms_line.path).exists(), f"THE FILE '{mms_line.path}' DOESN'T EXIST."

    def load_animation(self, blend_path: Path) -> bpy.types.Object:
        """Load the animation into the scene.

        This code copies the assets from the library and links it into the current blender
        context. Since the context data can be overwritten, we store a link in mms line.
        """

        if not blend_path.exists():
            raise Exception(f"Failed to find the library data '{str(blend_path)}'.")

        with bpy.data.libraries.load(str(blend_path)) as (data_from, data_to):
            data_to.objects = data_from.objects
            data_to.armatures = data_from.armatures
            data_to.actions = data_from.actions
            self.mms_line.data = data_to  # Store the link to current data.

        self.mms_line.data.armatures[0].name = self.mms_line.output_name

        # link the context
        for obj in self.mms_line.data.objects:
            assert isinstance(obj, bpy.types.Object)
            assert obj.type == 'ARMATURE'
            bpy.context.scene.collection.objects.link(obj)

        return self.mms_line.data.objects[0]

    def resample(self, timing: Union[Tuple[float, float], Tuple[float, bool]], use_rel_time: bool):
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
        name = source_armature.animation_data.action.name

        self.mms_line.original_frame_range = source_armature.animation_data.action.frame_range

        source_armature.animation_data.action.name = f"old_{name}"
        sampled_action = bpy.data.actions.new(name=name)

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

        self.mms_line.resampled_frame_range = source_armature.animation_data.action.frame_range

    def copy_armature(self):
        """Creates a copy of the armature and its animation.
        :return: the reference to the armature copy.
        """
        bpy_utils.select_object(self.src_armature)
        duplicate_armature = bpy_utils.duplicate(
            self.src_armature, self.mms_line.output_name
        )
        bpy.context.view_layer.update()
        return duplicate_armature
