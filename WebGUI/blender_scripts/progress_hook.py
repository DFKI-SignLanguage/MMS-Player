"""Executed by Blender before the MMS-Player main.py.
Prints a machine-readable line before rendering each frame, so that the web server can track the progress."""

import bpy
from bpy.app.handlers import persistent


@persistent
def _mmsweb_render_pre(scene, *_args):
    print(f"@@MMSWEB frame {scene.frame_current} {scene.frame_start} {scene.frame_end}", flush=True)


bpy.app.handlers.render_pre.append(_mmsweb_render_pre)
print("@@MMSWEB hook-installed", flush=True)
