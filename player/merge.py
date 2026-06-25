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
            target_armature_obj_name: str,
            target_action_name: str,
    ):
        """
        :param mms: MMS table containing all relevant gloss information.
        :param src_blendfile: The scene that contains the character assets.
        :param src_armature_obj_name: The name of the Armature object that we are going to animate.
        :param action_name: The name of new action to write the keyframes.
        """

        self.mms = mms
        self.src_armature_obj_name = target_armature_obj_name
        self.target_action_name = target_action_name


    def prepare_target_fcurves(self, reference_action_name: Optional[str] = None):
        """Create new empty fcurves in the action of the target armature.
         Copies the list of fcurves from the given action parameter.
         If the action name is not specified (default), the list of fcurves is taken from the first inflected gloss.
        """

        armature_obj = bpy.data.objects[self.src_armature_obj_name]
        bpy_utils.select_object(armature_obj)

        # By default, use the action of the first gloss as reference
        if reference_action_name is None:
            # Take one source action
            gloss = self.mms[self.mms.glosses[0]]
            reference_action_name = f"inflected_{gloss.output_name}"

        action = bpy.data.actions[reference_action_name]
        assert len(action.fcurves) != 0, f"The action {reference_action_name} has no animation data"

        for source_fcurve in action.fcurves:
            armature_obj.animation_data.action.fcurves.new(
                source_fcurve.data_path, index=source_fcurve.array_index
            )


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

    def append_action(self,
                          target_action_name: str,
                          source_action_name: str,
                          start: float) -> int:
        """Appends the data of a source action into a target action, starting from the given keyframe.
        Returns the keyframe number of the last added frame (acccording to the size of the source action).

        :param target_action_name: The target animation action.
        :param source_action_name: The source animation action.
        :param start: The starting keyframe for the given animation action
        :param print_debug: Debug flag.
        """

        source_action = bpy.data.actions[source_action_name]
        action_start, action_end = source_action.frame_range

        logger.info(f"Copying the keyframes from {source_action_name} into {target_action_name} at frame {start}")
        logger.info(f"Source action range is {action_start}-{action_end}")

        target_action = bpy.data.actions[target_action_name]

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

            if self.mms[gloss].datatype == "HOLD":
                # Should copy the animation here and update the
                prev_gloss_index = gloss[0] - 1
                prev_gloss_id = self.mms.glosses[prev_gloss_index]
                # end = self.mms[gloss].duration()[0]
                end_frame = self.perform_hold(
                        target_animation=self.target_action_name,
                        source_animation=f"inflected_{self.mms[prev_gloss_id].output_name}",
                        start=start,
                        end=end
                )
            else:
                # Combine the animation and get the new end_frame
                end_frame = self.append_action(
                    target_action_name=self.target_action_name,
                    source_action_name=f"inflected_{self.mms[gloss].output_name}",
                    start=start
                )

            last_gloss_end = end

            # We assume that the animation was already scaled. So the returned end_frame must be compatible with
            # the expected end frame. Compatible means +/- 1, according to rounding errors.
            assert end - 1 <= end_frame <= end + 1, f"{end} != {end_frame}"
