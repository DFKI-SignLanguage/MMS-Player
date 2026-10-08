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

import bpy
from pathlib import Path
from typing import List, Tuple, Optional

from .logging import logger
from .mms_parser import MMSLineDataInfo

# Naming convention prefixes for the actions present in a source gloss blend file.
BODY_ACTION_PREFIX = "updated_"
FACE_ACTION_PREFIX = "blendshapes_"


def _all_ids() -> list[bpy.types.ID]:
    """Return all the data-blocks currently present in bpy.data, regardless of their type."""

    ids: list[bpy.types.ID] = []
    for attr in dir(bpy.data):
        coll = getattr(bpy.data, attr, None)
        if isinstance(coll, bpy.types.bpy_prop_collection):
            ids.extend(id_ for id_ in coll if isinstance(id_, bpy.types.ID))
    return ids


def _all_id_pointers() -> set[int]:
    """Return the memory pointers of all the data-blocks currently present in bpy.data."""

    return {id_.as_pointer() for id_ in _all_ids()}


def load_gloss_actions(blend_path: Path, gloss_name: str, output_name: str) -> Tuple[bpy.types.Action, bpy.types.Action, float]:
    """Load the body and face actions of a gloss into the current blender context.

    The actions are renamed to "imported_<output_name>" and "imported_blendshapes_<output_name>",
    so that the same gloss can be loaded several times without collisions.

    :returns: A 3-tuple: the body action, the face action, and the duration of the gloss in seconds.
    """

    logger.info(f"Loading GLOSS animation data from '{blend_path}' ...")

    if not blend_path.exists():
        raise Exception(f"Failed to find the library data '{str(blend_path)}'.")

    # Take a snapshot of the existing data, so that we can identify (and later remove)
    # everything that is brought in together with the appended scene.
    pre_load_ids = _all_id_pointers()

    with bpy.data.libraries.load(str(blend_path)) as (data_from, data_to):
        if len(data_from.scenes) == 0:
            raise Exception(f"No scene found in '{str(blend_path)}'.")
        data_to.actions = data_from.actions
        data_to.scenes = data_from.scenes[:1]

    #
    # Retrieve the frames-per-second of the source scene.
    src_scene = data_to.scenes[0]
    scene_fps = src_scene.render.fps / src_scene.render.fps_base
    logger.info(f"Imported scene FPS: {scene_fps}")

    # Remove the scene and all its dependencies (objects, collections, meshes, ...), keeping only the actions.
    action_pointers = {action.as_pointer() for action in data_to.actions if action is not None}
    ids_to_remove = [id_ for id_ in _all_ids()
                     if id_.as_pointer() not in pre_load_ids and id_.as_pointer() not in action_pointers]
    bpy.data.batch_remove(ids_to_remove)

    #
    # Find the main body action by its known naming convention.
    body_action_name = BODY_ACTION_PREFIX + gloss_name
    if body_action_name not in bpy.data.actions:
        raise Exception(f"Body animation '{body_action_name}' not found in loaded scene.")
    body_action = bpy.data.actions[body_action_name]

    # Set the name of the imported action, avoiding duplicates and auto renaming in case of multiple glosses with the same name in the MMS
    body_action.name = "imported_" + output_name

    logger.info(f"Imported body action '{body_action.name}'")

    #
    # Check for the presence of the Blendshape face animation
    face_action_name = FACE_ACTION_PREFIX + gloss_name
    if face_action_name not in bpy.data.actions:
        raise Exception(f"Face animation '{face_action_name}' not found in loaded scene.")

    # Rename the action to a unique name
    face_action = bpy.data.actions[face_action_name]
    face_action.name = "imported_blendshapes_" + output_name

    #
    # Timing calculations
    frame_start, frame_end = body_action.frame_range
    duration_frames = frame_end - frame_start + 1
    duration_secs = duration_frames / scene_fps

    return body_action, face_action, duration_secs


def _bone_data_path_prefix(bone_name: str) -> str:
    return f'pose.bones["{bone_name}"]'


def _fcurves_of_bones(action: bpy.types.Action, bone_names: List[str]) -> List[bpy.types.FCurve]:
    """Return the fcurves of the given action animating any of the given bones."""

    prefixes = tuple(_bone_data_path_prefix(b) for b in bone_names)
    return [fc for fc in action.fcurves if fc.data_path.startswith(prefixes)]


def override_bone_fcurves(target_action: bpy.types.Action, source_action: bpy.types.Action, bone_names: List[str]) -> None:
    """Replace, in the target action, the fcurves of the given bones with the ones of the source action."""

    for target_fcurve in _fcurves_of_bones(target_action, bone_names):
        target_action.fcurves.remove(target_fcurve)

    for source_fcurve in _fcurves_of_bones(source_action, bone_names):
        target_fcurve = target_action.fcurves.new(data_path=source_fcurve.data_path, index=source_fcurve.array_index)
        target_fcurve.keyframe_points.add(len(source_fcurve.keyframe_points))
        for src_kfp, tgt_kfp in zip(source_fcurve.keyframe_points, target_fcurve.keyframe_points):
            tgt_kfp.co = src_kfp.co
            tgt_kfp.interpolation = src_kfp.interpolation
        target_fcurve.update()


def hold_bone_fcurves(target_action: bpy.types.Action, source_action: bpy.types.Action, bone_names: List[str], n_frames: int) -> None:
    """Replace, in the target action, the fcurves of the given bones with constant curves (keyed at frames 1 and n_frames)
    holding the value of the last keyframe of the source action."""

    for target_fcurve in _fcurves_of_bones(target_action, bone_names):
        target_action.fcurves.remove(target_fcurve)

    for source_fcurve in _fcurves_of_bones(source_action, bone_names):
        last_value = source_fcurve.keyframe_points[-1].co[1]
        target_fcurve = target_action.fcurves.new(data_path=source_fcurve.data_path, index=source_fcurve.array_index)
        target_fcurve.keyframe_points.insert(1, last_value, options={"FAST"})
        target_fcurve.keyframe_points.insert(n_frames, last_value, options={"FAST"})
        target_fcurve.update()


class ActionOperator:
    """This utility class has the methods to:

    1. Load the gloss animation(s) needed to realize a given MMSLine.
    2. Resample an action to a given target frame number
    """

    def __init__(self, mms_line_info: MMSLineDataInfo) -> None:

        self.mms_line_info = mms_line_info

        self.imported_main_armature_action: Optional[bpy.types.Action] = None
        self.imported_main_shapekeys_action: Optional[bpy.types.Action] = None

        self.imported_main_gloss_duration_secs: float

    def load_actions(self) -> None:
        """Load the gloss's actions into the scene.

        This code copies the assets from the library and links it into the current blender context.
        """

        blend_path = self.mms_line_info.maingloss_path

        if blend_path is None:
            raise Exception(f"No file path stored for '{self.mms_line_info.mms_line.output_name}'.")

        mms_line = self.mms_line_info.mms_line
        self.imported_main_armature_action, self.imported_main_shapekeys_action, self.imported_main_gloss_duration_secs = \
            load_gloss_actions(blend_path=blend_path, gloss_name=mms_line.name, output_name=mms_line.output_name)


def resample_action(src_action_name: str, target_action_name: str, target_framecount: int) -> bpy.types.Action:
    """Resample the given source action into a new action with the given target name.
    Operates purely on the action's f-curves, so it works regardless of what the action animates
    (armature bones, shape keys, ...) and requires no armature or bone-name knowledge.

    :param timing:  If use_rel_time is False, the timing is a tuple containing the MMS (framestart, frameend)
        already converted in frame position.
        If use_rel_time if True, the timing is a tuple (duration, pct),
        where the duration can be expressed as absolute vale in frames, or as a percentage of the original duration.
    :param use_rel_time: whether to use relative timing, or not.
    :param src_action_name: The name of the existing action
    :param target_action_name: The name of the action to be created
    :return: the newly created, resampled action.
    """

    src_action = bpy.data.actions[src_action_name]

    sampled_action = bpy.data.actions.new(name=target_action_name)

    # Mirror every fcurve from the source into the new action
    for src_fcurve in src_action.fcurves:
        sampled_action.fcurves.new(data_path=src_fcurve.data_path, index=src_fcurve.array_index)

    # Build sample points spanning the source frame range
    frame_start = int(src_action.frame_range[0])
    frame_end = int(src_action.frame_range[1])
    target_frame_count = int(target_framecount)
    ratio = (frame_end - frame_start) / (target_frame_count - 1)
    samples = [frame_start + x * ratio for x in range(target_frame_count)]

    for frame_number, sample in enumerate(samples):
        for src_fcurve in src_action.fcurves:
            sampled_value = src_fcurve.evaluate(sample)
            target_fcurve = sampled_action.fcurves.find(src_fcurve.data_path, index=src_fcurve.array_index)
            target_fcurve.keyframe_points.insert(frame_number + 1, sampled_value)

    assert target_action_name in bpy.data.actions

    return sampled_action
