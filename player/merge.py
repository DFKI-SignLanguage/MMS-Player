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

from typing import Optional, List
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
            target_armature_obj: bpy.types.Object,
            target_mesh_objs: List[bpy.types.Object],
            target_action_name: str,
            target_shapekeys_action_name: str
    ):
        """
        :param mms: MMS table containing all relevant gloss information.
        :param target_armature_obj: The armature object that will be animated with the sequence of glosses (skeleton).
        :param target_mesh_obj: The mesh object that will be animated with the sequence of glosses (mesh).
        :param target_action_name: The name of new action to write the keyframes for the armature.
        :param target_shapekeys_action_name: The name of new action to write the keyframes for the mesh animation.
        """

        self.mms = mms
        self.armature_obj = target_armature_obj
        self.action_name = target_action_name
        self.shapekeys_action_name = target_shapekeys_action_name

        # self.shape_keys: bpy.types.Key = self.mesh_obj.data.shape_keys
        # From the lits of target MESH objects, compose the list of target ShapeKeys structure
        self.shape_keys_list: List[bpy.types.Key] = [obj.data.shape_keys for obj in target_mesh_objs]

        self.target_action: Optional[bpy.types.Action] = None
        self.target_shapekeys_action: Optional[bpy.types.Action] = None


    def prepare_target_actions(self, reference_action: bpy.types.Action, reference_shapekeys_action: bpy.types.Action):
        """Create new empty actions for the target armature and mesh objects.
         Copies the list of fcurves from the given actions parameter.
        """

        #
        # Initialize the ARMATURE
        self.target_action = bpy.data.actions.new(self.action_name)

        for source_fcurve in reference_action.fcurves:
            self.target_action.fcurves.new(source_fcurve.data_path, index=source_fcurve.array_index)

        # Assign the action to the ARMATURE object
        self.armature_obj.animation_data_create()
        assert self.armature_obj.animation_data is not None
        self.armature_obj.animation_data.action = self.target_action


        #
        # Initialize the MESH
        self.target_shapekeys_action = bpy.data.actions.new(self.shapekeys_action_name)

        for source_fcurve in reference_shapekeys_action.fcurves:
            self.target_shapekeys_action.fcurves.new(source_fcurve.data_path, index=source_fcurve.array_index)

        # Assign the shape key action to the MESH objects
        # self.shape_keys.animation_data_create()
        # self.shape_keys.animation_data.action = self.target_shapekeys_action
        for sk in self.shape_keys_list:
            sk.animation_data_create()
            assert sk.animation_data is not None
            sk.animation_data.action = self.target_shapekeys_action


    def perform_hold(self,
                     target_action: bpy.types.Action,
                     source_action: bpy.types.Action,
                     start: float,
                     end: float,
                     ) -> int:

        logger.info(f"Performing HOLD Operation in range {start}-{end}. Last frame from {source_action.name}.")

        for source_fcurve in source_action.fcurves:
            target_curve = target_action.fcurves.find(
                    source_fcurve.data_path, index=source_fcurve.array_index
                    )

            # Get the last keyframe points
            last_keyframe_idx = len(source_fcurve.keyframe_points) - 1
            last_keyframe_point = source_fcurve.keyframe_points[last_keyframe_idx]

            # Insert the two keyframes at the start and end positions
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

    def append_action(self,
                          target_action: bpy.types.Action,
                          source_action: bpy.types.Action,
                          start: float) -> int:
        """Appends the data of a source action into a target action, starting from the given keyframe.
        Returns the keyframe number of the last added frame (acccording to the size of the source action).

        :param target_action_name: The target animation action.
        :param source_action_name: The source animation action.
        :param start: The starting keyframe for the given animation action
        :param print_debug: Debug flag.
        """

        action_start, action_end = source_action.frame_range

        logger.info(f"Copying the keyframes from {source_action.name} into {target_action.name} at frame {start}")
        logger.info(f"Source action range is {action_start}-{action_end}")


        # Iterate over all the animation curves and copy the data
        for source_fcurve in source_action.fcurves:
            target_fcurve = target_action.fcurves.find(
                source_fcurve.data_path, index=source_fcurve.array_index
            )
            # print(f"After searching {source_fcurve.data_path} --> {target_fcurve}")
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

        end = int(action_end) + start - 1

        logger.info(f"Last written frame: {end}")

        return end

    def realize_mms(self, use_rel_time: bool = False):
        """Generate the timing data for individual glosses and merge them into final track.
        """

        # `last_gloss_end` holds the last frame number of the previous gloss.
        # In relative time mode, combined with transition duration, it allows to compute the start of the next gloss.
        last_gloss_end = 1

        for gloss in self.mms.glosses:

            # TODO -- this was actually tested before, and anyway not used here. Remove?
            if not self.mms[gloss].path.exists():
                print("TODO: This should be fixed in the future updates.")
                continue

            if use_rel_time:
                start = last_gloss_end + self.mms[gloss].transition()
                duration_or_prop, is_relative = self.mms[gloss].duration()
                if is_relative:
                    # In this case the duration is a fraction
                    assert 0 <= duration_or_prop
                    # Compute the estimated duration according to the sign duration
                    fs, fe = self.mms[gloss].original_frame_range
                    dur_orig = (fe - fs)
                    duration_or_prop = dur_orig * duration_or_prop

                end = start + duration_or_prop
            else:
                start, end = self.mms[gloss].timing()
                # We start filling our timeline from frame 1
                start += 1
                end += 1

            logger.info(f"Merging gloss {self.mms[gloss].output_name} in frames from {start} to {end}")

            if self.mms[gloss].is_hold:
                # Should copy the animation here and update the
                #prev_gloss_index = gloss[0] - 1
                #prev_gloss_id = self.mms.glosses[prev_gloss_index]
                # end = self.mms[gloss].duration()[0]
                end_frame = self.perform_hold(
                    target_action=self.target_action,
                    source_action=bpy.data.actions[f"inflected_{self.mms[gloss].output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start,
                    end=end
                )
                end_frame = self.perform_hold(
                    target_action=self.target_shapekeys_action,
                    source_action=bpy.data.actions[f"resampled_blendshapes_{self.mms[gloss].output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start,
                    end=end
                )

            else:
                # Combine the animation and get the new end_frame
                end_frame = self.append_action(
                    target_action=self.target_action,
                    source_action=bpy.data.actions[f"inflected_{self.mms[gloss].output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start
                )

                end_frame_shapekeys = self.append_action(
                    target_action=self.target_shapekeys_action,
                    source_action=bpy.data.actions[f"resampled_blendshapes_{self.mms[gloss].output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start
                )

            last_gloss_end = end

            # We assume that the animation was already scaled. So the returned end_frame must be compatible with
            # the expected end frame. Compatible means +/- 1, according to rounding errors.
            assert end - 1 <= end_frame <= end + 1, f"{end} != {end_frame}"
