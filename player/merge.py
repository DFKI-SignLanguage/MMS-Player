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
# This module contains the functions to merge the inflected signs into a single animation.
#

import bpy
import json

from pathlib import Path
from typing import Optional
from .mms_parser import MMS
from .logging import logger
from . import bpy_utils


def load_json(fp):
    """Read json file and load it."""
    with open(fp, "r") as stream:
        dump = json.load(stream)
        stream.close()
    return set(dump["ignore_list"])


class Glue:
    """Handle the compilation of inflected glosses.

    Glue reads the appropriate timing information from the MMS table
    and copies the keyframes from these individual glosses to a new
    keyframe animation track.
    """

    def __init__(
            self,
            mms: MMS,
            ignore_bone_list: str,
            src_blendfile: str,
            action_name: str,
    ):
        """
        :param mms: MMS table containing all relevant gloss information
        :param src_blendfile: The scene that contains the character assets.
        :param action_name: The name of new action to write the keyframes.
        """

        self.armature_obj_name = "skeleton #5"
        self.action_name = action_name
        self._duplicate_armature = "final_armature"
        self.mms = mms
        # TODO -- this is unused! Forgotten or to be used in the future?
        self.ignore_list = load_json(ignore_bone_list)
        self.src_blendfile = src_blendfile

        self.initialize_scene()
        self.initialize_mesh()

    def initialize_scene(self):
        """Blender scene initialization.

        Copy the objects from original scene to the current context.
        Link them into the current context to work on them.
        """

        # Select all objects and delete them.
        # Will leave only the armature data and the actions.
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        # Load objects from the reference scene (nice character and lights)
        with bpy.data.libraries.load(self.src_blendfile) as (data_from, data_to):
            data_to.objects = data_from.objects
            data_to.worlds = data_from.worlds
        for obj in data_to.objects:
            bpy.context.scene.collection.objects.link(obj)
        bpy.context.scene.world = data_to.worlds[0]

    def initialize_mesh(self):
        """Replace the name in the original mesh and create a new action.

        The original names are "Bone Pelvis". This name doesn't work for the
        skeletal animations which are of format "Bone_Pelvis". Thus, we modify
        the name of bones in the original mesh itself as it is one time operation.
        """

        mesh_armature = bpy.data.objects[self.armature_obj_name]
        assert isinstance(mesh_armature, bpy.types.Object)
        assert mesh_armature.type == "ARMATURE"
        for bone in mesh_armature.pose.bones:
            bone.name = bone.name.replace(" ", "_")
            bone.rotation_mode = "ZXY"
        mesh_armature.animation_data_create()
        action_ref = bpy.data.actions.new(self.action_name)
        mesh_armature.animation_data.action = action_ref

    def perform_hold(self,
                     target_animation: str,
                     source_animation: str,
                     start: float,
                     end: float,
                     ) -> int:

        logger.info(f"Performing HOLD Operation in range {start}-{end}. Last frame from {source_animation}.")

        source_action = bpy.data.actions[source_animation]
        target_action = bpy.data.actions[target_animation]

        for source_fcurve in source_action.fcurves:
            target_curve = target_action.fcurves.find(
                    source_fcurve.data_path, index=source_fcurve.array_index
                    )
            # Get the last keyframe points
            last_keyframe_idx = len(source_fcurve.keyframe_points) - 1
            last_keyframe_point = source_fcurve.keyframe_points[last_keyframe_idx]
            # Insert the two keyframes at the specified positions
            target_curve.keyframe_points.insert(
                    frame=start,
                    value=last_keyframe_point.co[1],
                    options={"FAST"}
                    )
            target_curve.keyframe_points.insert(
                    frame=end,
                    value=last_keyframe_point.co[1],
                    options={"FAST"}
                    )

        return end

    def combine_animation(self,
                          target_animation: str,
                          source_animation: str,
                          start: float) -> int:
        """Combine the animations.

        :param target_animation: The target animation action.
        :param source_animation: The source animation action.
        :param start: The starting keyframe for the given animation action
        :param print_debug: Debug flag.
        """
        source_action = bpy.data.actions[source_animation]
        action_start, action_end = source_action.frame_range

        logger.info(f"Copying the keyframes from {source_animation} into {target_animation} at frame {start}")
        logger.info(f"Source action range is {action_start}-{action_end}")

        target_action = bpy.data.actions[target_animation]

        # Iterate over all the animation curves
        for source_fcurve in source_action.fcurves:
            target_fcurve = target_action.fcurves.find(
                source_fcurve.data_path, index=source_fcurve.array_index
            )
            # Copy, 1-by-1, all the keyframes
            for i, src_kfp in enumerate(source_fcurve.keyframe_points):
                # Co-ordinates of the control points, starts from 0.
                # For the first keyframe_point, co[0] = 1. Therefore, adjust for off-by-1 error
                target_fcurve.keyframe_points.insert(
                    frame=src_kfp.co[0] + start - 1,
                    value=src_kfp.co[1],
                    options={"FAST"},
                )
            target_fcurve.update()

        end = int(action_end) + start

        logger.info(f"Last written frame: {end}")

        return end

    def create_new_fcurves(self, action_name: Optional[str] = None):
        """Create a new action with empty fcurves in the target armature.
         Copies the list of fcurves from the given action parameter.
         If the action name is not specified (default), the list of fcurves is taken from the first inflected gloss.
        """

        armature_obj = bpy.data.objects[self.armature_obj_name]
        bpy_utils.select_object(armature_obj)
        bpy.context.object.name = armature_obj.name
        bpy.context.object.data.name = armature_obj.name

        # By default, use the action of the first gloss as reference
        if action_name is None:
            # Take one source action
            gloss = self.mms[self.mms.glosses[0]]
            action_name = f"inflected_{gloss.output_name}"

        action = bpy.data.actions[action_name]
        assert len(action.fcurves) != 0, f"The action {action_name} has no animation data"

        for source_fcurve in action.fcurves:
            armature_obj.animation_data.action.fcurves.new(
                source_fcurve.data_path, index=source_fcurve.array_index
            )

    def merge_animation(self, use_rel_time: bool = False):
        """Generate the timing data for individual gloss and merge into final track.
        """

        # `last_gloss_end` holds the last frame number of the previous gloss.
        # In relative time mode, combined with transition duration, it allows to compute the start of the next gloss.
        last_gloss_end = 1

        for gloss in self.mms.glosses:

            # TODO -- this was actually teste before, and anyway not used here. Remove?
            if not self.mms[gloss].path.exists():
                print("TODO: This should be fixed in the future updates.")
                continue

            if use_rel_time:
                start = last_gloss_end + self.mms[gloss].transition()
                duration, is_relative = self.mms[gloss].duration()
                if is_relative:
                    # In this case the duration is a fraction
                    assert 0 <= duration <= 1
                    # Compute the estimated duration according to the sampled
                    fs, fe = self.mms[gloss].original_frame_range
                    dur_orig = (fe - fs)
                    duration = dur_orig * duration

                end = start + duration
            else:
                start, end = self.mms[gloss].timing()
                # We start filling our timeline from frame 1
                start += 1
                end += 1

            logger.info(f"Merging gloss {self.mms[gloss].output_name} in frames from {start} to {end}")

            if self.mms[gloss].datatype == "HOLD":
                # Should copy the animation here and update the
                prev_gloss_index = gloss[0] - 1
                prev_gloss_id = self.mms.glosses[prev_gloss_index]
                # end = self.mms[gloss].duration()[0]
                end_frame = self.perform_hold(
                        target_animation=self.action_name,
                        source_animation=f"inflected_{self.mms[prev_gloss_id].output_name}",
                        start=start,
                        end=end
                )
            else:
                # Combine the animation and get the new end_frame
                end_frame = self.combine_animation(
                    target_animation=self.action_name,
                    source_animation=f"inflected_{self.mms[gloss].output_name}",
                    start=start
                )

            last_gloss_end = end

            # We assume that the animation was already scaled. So the returned end_frame must be compatible with
            # the expected end frame. Compatible means +/- 1, according to rounding errors.
            assert end - 1 <= end_frame <= end + 1, f"{end} != {end_frame}"
