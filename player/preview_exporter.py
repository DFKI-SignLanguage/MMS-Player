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

"""Export of the realized animation into a compact JSON format meant for real-time playback
(e.g., with Three.js) on the character exported as glTF by `tools/export_character_glb.py`.

Every bone transform is sampled per frame and written in the same local (parent-relative) space that the
Blender glTF exporter (with +Y up) uses for joint nodes. A player can therefore directly assign the values
to the `position`, `quaternion`, and `scale` of the glTF joint nodes, without any rest-pose computation.

Format (all numbers are plain floats; per-frame arrays are flattened over bones):

    {
      "format": "mms-preview", "version": 1,
      "fps": 30.0, "frame_start": 1, "frame_count": N,
      "bones": ["Bone", "Bone_Pelvis", ...],
      "tracks": {
        "position":   [[x, y, z,  x, y, z, ...], ...],       # 3 values per bone, one list per frame
        "quaternion": [[x, y, z, w,  x, y, z, w, ...], ...],  # 4 values per bone (Three.js/glTF order)
        "scale":      [[x, y, z,  ...], ...]                  # 3 values per bone
      },
      "morph_names": ["eyeBlinkLeft", ...],
      "morphs": [[w0, w1, ...], ...],                          # one weight per morph name, one list per frame
      "glosses": [{"index": 0, "gloss": "INDEX", "start": 1.0, "end": 24.0}, ...]  # frame ranges
    }
"""

import bpy
import json
from mathutils import Matrix
from pathlib import Path

from typing import List, Optional


FORMAT_NAME = "mms-preview"
FORMAT_VERSION = 1

# Number of decimals stored in the JSON file.
DECIMALS = 5

# The same Z-up to Y-up basis change used by the Blender glTF exporter (see `gltf2_blender_gather_tree.py`).
# The exporter computes the joint world matrices as `arm_world @ pbone.matrix @ AXIS_BASIS_CHANGE` and the
# armature object node is converted with the same basis. Hence, the local matrix of a child joint is just
# `parent.matrix^-1 @ pbone.matrix`, while the local matrix of a root joint is `AXIS_BASIS_CHANGE @ pbone.matrix`.
AXIS_BASIS_CHANGE = Matrix(((1.0, 0.0, 0.0, 0.0),
                            (0.0, 0.0, 1.0, 0.0),
                            (0.0, -1.0, 0.0, 0.0),
                            (0.0, 0.0, 0.0, 1.0)))


def _r(v: float) -> float:
    out = round(v, DECIMALS)
    # Avoid writing "-0.0"
    return 0.0 if out == 0 else out


def export_preview_animation(armature_obj: bpy.types.Object,
                             shapekeys_mesh_obj: Optional[bpy.types.Object],
                             frame_start: int,
                             frame_end: int,
                             out_json_path: Path,
                             gloss_timeline: Optional[list] = None) -> None:
    """Sample the current animation of the given armature (and of the shape keys of the given mesh) and save it
    as `mms-preview` JSON file.

    :param armature_obj: The animated armature.
    :param shapekeys_mesh_obj: A mesh whose shape keys values are exported as morph target weights (can be None).
    :param frame_start: First frame to export (included).
    :param frame_end: Last frame to export (included).
    :param out_json_path: Destination file.
    :param gloss_timeline: Optional list of `GlossSegment`, stored as information for the player.
    """

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base

    pose_bones: List[bpy.types.PoseBone] = list(armature_obj.pose.bones)
    bone_names = [pb.name for pb in pose_bones]

    morph_names: List[str] = []
    key_blocks = None
    if shapekeys_mesh_obj is not None and shapekeys_mesh_obj.data.shape_keys is not None:
        shape_keys = shapekeys_mesh_obj.data.shape_keys
        key_blocks = [kb for kb in shape_keys.key_blocks if kb != shape_keys.reference_key]
        morph_names = [kb.name for kb in key_blocks]

    positions = []
    quaternions = []
    scales = []
    morphs = []

    for f in range(frame_start, frame_end + 1):
        scene.frame_set(f)

        frame_pos = []
        frame_quat = []
        frame_scale = []
        for pb in pose_bones:
            if pb.parent is None:
                local = AXIS_BASIS_CHANGE @ pb.matrix
            else:
                local = pb.parent.matrix.inverted_safe() @ pb.matrix
            loc, rot, sca = local.decompose()
            frame_pos.extend((_r(loc.x), _r(loc.y), _r(loc.z)))
            frame_quat.extend((_r(rot.x), _r(rot.y), _r(rot.z), _r(rot.w)))
            frame_scale.extend((_r(sca.x), _r(sca.y), _r(sca.z)))
        positions.append(frame_pos)
        quaternions.append(frame_quat)
        scales.append(frame_scale)

        if key_blocks is not None:
            morphs.append([_r(kb.value) for kb in key_blocks])

    out = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "fps": fps,
        "frame_start": frame_start,
        "frame_count": frame_end - frame_start + 1,
        "bones": bone_names,
        "tracks": {
            "position": positions,
            "quaternion": quaternions,
            "scale": scales,
        },
        "morph_names": morph_names,
        "morphs": morphs,
        "glosses": [
            {"index": seg.index, "gloss": seg.name, "start": seg.start_frame, "end": seg.end_frame}
            for seg in (gloss_timeline or [])
        ],
    }

    with open(out_json_path, "w") as jsonfile:
        json.dump(obj=out, fp=jsonfile, separators=(",", ":"))
