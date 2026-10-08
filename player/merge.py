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

import math
from pathlib import Path

import bpy

from dataclasses import dataclass
from typing import Callable, Optional, Tuple, List, Dict

from .mms_parser import ARM_OVERRIDE_COLUMNS, MMS, MMSLine
from .action_utils import load_gloss_actions

from .logging import logger



@dataclass
class GlossSegment:
    """The frame range, on the final realized timeline, occupied by a single MMS row (gloss).

    Produced by `Glue.realize_mms()`. Used e.g. to drive the optional gloss subtitle panel.
    """
    index: int  # The MMS row number (n), starting from 0.
    name: str  # The gloss text realized for this row.
    start_frame: float
    end_frame: float


class MMSLineDataInfo:
    """Auxiliary information to an MMSLine, holding information created and retrieved only at run-time.
    """

    def __init__(self, mms_line: MMSLine):

        self.mms_line = mms_line

        #
        # File paths
        #
        # Filled later while scanning or loading the blend files
        self.maingloss_path: Optional[Path] = None  # Path to the Blend scene containing the gloss animation data for this MMS line.
        # Paths to the Blend scenes of the glosses overriding the arms. Keys are "dom" and "ndom". <HOLD> overrides have no path.
        self.arm_override_paths: Dict[str, Path] = {}

        #
        # Imported actions info
        #
        # Armature action for main gloss
        self.imported_maingloss_armature_action: Optional[bpy.types.Action] = None
        # ShapeKeys action for main gloss
        self.imported_maingloss_shapekeys_action: Optional[bpy.types.Action] = None
        # Original framerate of the main gloss imported action
        self.imported_maingloss_frame_range: Optional[Tuple[float, float]] = None
        # Store also the framerate of the source Blenderr file, to proper resamplings among different FPS.
        self.imported_maingloss_duration_secs: float

        #
        # Timing conmputations
        #
        # The new duration of this maingloss, in frames
        self.resampled_duration_frames: int
        # The target framerange on the final timeline
        self.target_frame_range: Optional[Tuple[int, int]] = None



    def compose_file_paths(self, dictionary_root: Path) -> None:
        """
        Compose the gloss path and verify that the path exists.
        If the required file doesn't exist, an Exception is thrown.
        """

        maingloss_blend_file = f"{self.mms_line.name}.blend"

        self.maingloss_path = dictionary_root / self.mms_line.datatype / "trimmed" / maingloss_blend_file
        assert self.maingloss_path is not None

        if not self.maingloss_path.exists():
            raise Exception(f"Expected gloss file '{self.maingloss_path}' not present for '{self.mms_line.name}'.")

        for side, arm_override in self.mms_line.arm_overrides.items():
            if arm_override.is_hold:
                continue
            assert arm_override.name is not None and arm_override.datatype is not None
            arm_path = dictionary_root / arm_override.datatype / "trimmed" / f"{arm_override.name}.blend"
            if not arm_path.exists():
                raise Exception(f"Expected gloss file '{arm_path}' not present for {ARM_OVERRIDE_COLUMNS[side]} '{arm_override.name}'.")
            self.arm_override_paths[side] = arm_path

    def load_actions(self) -> None:
        """Load the gloss's actions into the scene.

        This code copies the assets from the library and links it into the current blender context.
        """

        blend_path = self.maingloss_path

        if blend_path is None:
            raise Exception(f"No file path stored for '{self.mms_line.output_name}'.")

        mms_line = self.mms_line
        self.imported_maingloss_armature_action, self.imported_maingloss_shapekeys_action, self.imported_maingloss_duration_secs = \
            load_gloss_actions(blend_path=blend_path, gloss_name=mms_line.name, output_name=mms_line.output_name)

    def compute_target_frame_range(self, use_rel_time: bool, last_gloss_end_frame: int, target_fps: float) -> None:

        if use_rel_time:
            # If relative timing is used, we use the duration and transition properties of the MMS
            duration_val, duration_relative = self.mms_line.duration()
            if duration_relative:
                duration_secs = self.imported_maingloss_duration_secs * duration_val
                # frame_start = int(src_action.frame_range[0])
                # frame_end = int(src_action.frame_range[1])
                # target_frame_count = math.ceil(duration_or_prop * (frame_end - frame_start) + 1)
            else:
                duration_secs = duration_val

            transition_secs = self.mms_line.transition()

            # Consider total timing, then compute the transition in frames as approximated frame count and derive then the duration in frames.
            tot_time_secs = duration_secs + transition_secs

            tot_time_frames = math.ceil(tot_time_secs * target_fps)

            # Give priority /maximize the framecount for the 
            self.resampled_duration_frames = math.ceil(duration_secs * target_fps)

            transition_frames = tot_time_frames - self.resampled_duration_frames

            self.target_frame_range = ( \
                last_gloss_end_frame + transition_frames, \
                last_gloss_end_frame + transition_frames + self.resampled_duration_frames - 1 \
            )

        else:
            # Here the absolute timing is used. Get it from the two start/end columns of the MMS
            start_secs, end_secs = self.mms_line.timing()

            # Consider the target scene FPS to get the approximation in frames
            #
            # Approximate to the last integer frame. Example for 60 fps (frame duration = 0.01666_)
            # math.floor(0.0 * 60.0) --> 0
            # math.floor(0.0166 * 60.0) --> 0
            # math.floor(0.0167 * 60.0) --> 1
            # ...
            # math.floor(0.9999 * 60.0) --> 59
            # math.floor(1.0 * 60.0) --> 60
            #
            # We add +1 because we start filling our timeline from frame 1
            self.target_frame_range = ( \
                math.floor(start_secs * target_fps) + 1, \
                math.floor(end_secs * target_fps) + 1 \
            )

            # The duration is a direct consequence
            self.resampled_duration_frames = self.target_frame_range[1] - self.target_frame_range[0] + 1

        assert self.target_frame_range is not None
        # The duration in frames is related to the frame range
        assert self.resampled_duration_frames == self.target_frame_range[1] - self.target_frame_range[0] + 1
        assert self.target_frame_range[1] >= self.target_frame_range[0]

        if self.resampled_duration_frames == 0:
            raise Exception("A gloss execution must last at least 1 frame.")

        if self.target_frame_range[0] < last_gloss_end_frame:
            raise Exception(f"Negative transition between glosses. New gloss start frame ({self.target_frame_range[0]}) is less than the last gloss end frame ({last_gloss_end_frame}).")


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
        :param target_armature_obj: The armature object that will be animated with the sequence of glosses (Skeleton).
        :param target_mesh_objs: The list of mesh objects that will be animated with the sequence of glosses (ShapeKeys).
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

        # Filled later during target actions preparation
        self.target_action: Optional[bpy.types.Action] = None
        self.target_shapekeys_action: Optional[bpy.types.Action] = None

        # Filled later by realize_mms(): the frame range of each gloss on the final timeline.
        self.gloss_timeline: List[GlossSegment] = []


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
                     data_path_filter: Optional[Callable[[str], bool]] = None,
                     ) -> int:
        """:param data_path_filter: If given, only the source fcurves whose data_path satisfies the filter are processed."""

        logger.info(f"Performing HOLD Operation in range {start}-{end}. Last frame from {source_action.name}.")

        for source_fcurve in source_action.fcurves:
            if data_path_filter is not None and not data_path_filter(source_fcurve.data_path):
                continue
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
                          start: float,
                          data_path_filter: Optional[Callable[[str], bool]] = None) -> int:
        """Appends the data of a source action into a target action, starting from the given keyframe.
        Returns the keyframe number of the last added frame (acccording to the size of the source action).

        :param target_action_name: The target animation action.
        :param source_action_name: The source animation action.
        :param start: The starting keyframe for the given animation action
        :param data_path_filter: If given, only the source fcurves whose data_path satisfies the filter are copied.
        """

        action_start, action_end = source_action.frame_range

        logger.info(f"Copying the keyframes from {source_action.name} into {target_action.name} at frame {start}")
        logger.info(f"Source action range is {action_start}-{action_end}")


        # Iterate over all the animation curves and copy the data
        for source_fcurve in source_action.fcurves:
            if data_path_filter is not None and not data_path_filter(source_fcurve.data_path):
                continue
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

    def realize_mms(self, rows_info: Dict[Tuple[int, str], MMSLineDataInfo], arm_bones: Dict[str, List[str]]):
        """Generate the timing data for individual glosses and merge them into final track.

        :param arm_bones: The bones of the "dom" and "ndom" arms, used to realize the (n)domarm overrides of <HOLD> rows.
        """

        for row_idx in self.mms.row_indices:

            mms_row = self.mms[row_idx]
            mms_row_info = rows_info[row_idx]

            assert mms_row_info.target_frame_range is not None
            start, end = mms_row_info.target_frame_range

            logger.info(f"Merging gloss {mms_row.output_name} in frames from {start} to {end}")

            # For a <HOLD> row, `.name` has been overwritten (in ensure_mocap_data_files()) to the
            # held gloss's name, so that the mocap file path resolves correctly. Report "<HOLD>"
            # instead, so the panel reflects what's actually being realized for this row.
            gloss_name = "<HOLD>" if mms_row.is_hold else mms_row.name
            for side, arm_override in mms_row.arm_overrides.items():
                arm_gloss_name = "<HOLD>" if arm_override.is_hold else arm_override.name
                gloss_name += f" +{side}:{arm_gloss_name}"
            self.gloss_timeline.append(
                GlossSegment(index=row_idx[0], name=gloss_name, start_frame=start, end_frame=end)
            )

            if mms_row.is_hold:

                # The arms overridden by another gloss must play their animation, while the rest of the body holds.
                animated_arm_prefixes = tuple(
                    f'pose.bones["{bone_name}"]'
                    for side, arm_override in mms_row.arm_overrides.items() if not arm_override.is_hold
                    for bone_name in arm_bones[side]
                )

                inflected_action = bpy.data.actions[f"inflected_{mms_row.output_name}"]  # TODO -- somehow remove this hard-coded name
                end_frame = self.perform_hold(
                    target_action=self.target_action,
                    source_action=inflected_action,
                    start=start,
                    end=end,
                    data_path_filter=lambda data_path: not data_path.startswith(animated_arm_prefixes)
                )
                if len(animated_arm_prefixes) > 0:
                    self.append_action(
                        target_action=self.target_action,
                        source_action=inflected_action,
                        start=start,
                        data_path_filter=lambda data_path: data_path.startswith(animated_arm_prefixes)
                    )
                end_frame = self.perform_hold(
                    target_action=self.target_shapekeys_action,
                    source_action=bpy.data.actions[f"resampled_blendshapes_{mms_row.output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start,
                    end=end
                )

            else:
                # Combine the animation and get the new end_frame
                end_frame = self.append_action(
                    target_action=self.target_action,
                    source_action=bpy.data.actions[f"inflected_{mms_row.output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start
                )

                end_frame_shapekeys = self.append_action(
                    target_action=self.target_shapekeys_action,
                    source_action=bpy.data.actions[f"resampled_blendshapes_{mms_row.output_name}"],  # TODO -- somehow remove this hard-coded name
                    start=start
                )

            # We assume that the animation was already scaled. So the returned end_frame must be compatible with
            # the expected end frame. Compatible means +/- 1, according to rounding errors.
            assert end - 1 <= end_frame <= end + 1, f"{end} != {end_frame}"
