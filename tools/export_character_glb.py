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

"""Export the character of the template scene (assets/gloria-260813.blend) as glTF binary (GLB),
for real-time playback of the animations exported with `main.py --export-preview-json`.

The scene is prepared exactly as in the MMS realization pipeline (same bone names), and only the
character (armature + skinned meshes) and the render camera are exported, without animation.

Usage:
    blender --background --python tools/export_character_glb.py -- [--out assets/gloria-260813.glb]
"""

import argparse
import sys
from pathlib import Path

import bpy

MMS_PLAYER_ROOT_PATH = Path(__file__).resolve().parent.parent
sys.path.append(str(MMS_PLAYER_ROOT_PATH))

from main import initialize_scene, initialize_target_armature  # noqa: E402
from main import DEFAULT_BLEND_SCENE_PATH, TARGET_ARMATURE_NAME, RENDER_CAMERA_NAME  # noqa: E402


DEFAULT_OUT_PATH = DEFAULT_BLEND_SCENE_PATH.with_suffix(".glb")


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT_PATH), help="Output GLB file.")
    parser.add_argument("--res-x", type=int, default=1080, help="Render width, used for the camera aspect ratio.")
    parser.add_argument("--res-y", type=int, default=1920, help="Render height, used for the camera aspect ratio.")
    args = parser.parse_args(argv)

    initialize_scene()
    initialize_target_armature()

    armature = bpy.data.objects[TARGET_ARMATURE_NAME]
    camera = bpy.data.objects[RENDER_CAMERA_NAME]

    # The character meshes: all the meshes deformed by the target armature.
    meshes = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers)
    ]
    print(f"Exporting armature '{armature.name}', camera '{camera.name}', meshes {sorted(m.name for m in meshes)}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in [armature, camera] + meshes:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature

    # The camera field of view is exported according to the scene aspect ratio: use the same as the video renders.
    bpy.context.scene.render.resolution_x = args.res_x
    bpy.context.scene.render.resolution_y = args.res_y

    out_path = Path(args.out).absolute()
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=False,
        export_skins=True,
        export_morph=True,
        export_morph_normal=True,
        export_animations=False,
        export_cameras=True,
        export_lights=False,
    )
    print(f"Character exported to '{out_path}'.")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(argv)
