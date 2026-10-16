"""Executed by Blender to compute the original duration (in seconds) of dictionary glosses.

Usage: blender --background --python gloss_durations.py -- <items.json>
where items.json is a list of {"id": ..., "name": ..., "path": ...}.
For each item, prints a line: @@MMSWEB duration {"id": ..., "secs": ...}
"""

import json
import sys

import bpy

BODY_ACTION_PREFIX = "updated_"

items = json.load(open(sys.argv[sys.argv.index("--") + 1]))

for i, item in enumerate(items):
    out = {"id": item["id"]}
    try:
        action_name = BODY_ACTION_PREFIX + item["name"]
        with bpy.data.libraries.load(item["path"], link=True) as (data_from, data_to):
            if action_name not in data_from.actions:
                raise Exception(f"Action '{action_name}' not found")
            data_to.actions = [action_name]
            data_to.scenes = data_from.scenes[:1]
        action = data_to.actions[0]
        scene = data_to.scenes[0]
        fps = scene.render.fps / scene.render.fps_base
        frame_start, frame_end = action.frame_range
        out["secs"] = (frame_end - frame_start + 1) / fps
        bpy.data.libraries.remove(action.library)
    except Exception as e:
        out["error"] = str(e)
    print("@@MMSWEB duration " + json.dumps(out), flush=True)
    print(f"@@MMSWEB progress {i + 1} {len(items)}", flush=True)
