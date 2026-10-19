# MMS-Player Web GUI

A browser-based editor for MMS instances. The server has access to the Dictionary of signs and to the MMS-Player. The browser edits the MMS table and shows the animated result.
See [Description.md](Description.md) for the original specification.

## Requirements

* Python 3.9+ with Flask (`pip install -r requirements.txt`). This project doesn't need the parent project's Python requirements.
* Blender 4.2 LTS (the same version used by the MMS-Player).
* A release of the Dictionary of signs.
* The MMS-Player. By default this is the parent folder of `WebGUI/`.

## Running

```bash
pip install -r requirements.txt

export BLENDER_EXE=/Applications/blender-4.2.23/Blender.app/Contents/MacOS/Blender
python server.py \
  --dictionary-dir path/to/DictionaryGeneration-deploy-YYMMDD \
  --project-dir path/to/my-mms-project
```

Then open <http://localhost:5050/>.

| Option | Default | Meaning |
|---|---|---|
| `--dictionary-dir` | `$DICTIONARY_DIR` | Folder of the Dictionary of signs |
| `--player-dir` | parent folder | Folder of the MMS-Player (`main.py`) |
| `--project-dir` | (required) | Where MMS instances, renders, and caches are stored. Created if it doesn't exist. |
| `--blender-exe` | `$BLENDER_EXE` | Blender executable |
| `--host` / `--port` | `127.0.0.1` / `5050` | Use `--host 0.0.0.0` to accept remote connections. The server has no authentication. |
| `--render-workers` | 1 | Number of videos rendered in parallel |
| `--render-size-pct` | 50 | Default size of the generated videos (percentage of 1080×1920) |
| `--preview-size-pct` | 25 | Size of the single-sign previews |
| `--target-fps` | 30 | FPS of the generated videos and previews. Saved in `server_options.local.json` and reused at the next start |

Persistent options are stored in `WebGUI/server_options.local.json` (git-ignored). The file is created at the first start. Edit it directly or pass the option on the command line, which also updates the file.

Options available only in the file:

| Option | Default | Meaning |
|---|---|---|
| `font_size_px` | 13 | Base font size (pixels) of the web interface. All the other text sizes, and the table row heights, scale with it. Takes effect when the server restarts and the page is reloaded. |

### Project folder layout

```
my-mms-project/
  *.mms.csv              MMS instances saved from the editor
  renders/               generated videos, each next to a copy of the MMS that produced it and its 3D animation data
  .mmsweb-cache/
    previews/<class>/    single-sign preview videos (rendered on first request)
    anims/               the last 20 3D previews (animation data and MMS)
    durations.json       original duration of each sign, used by the timeline
```

## Using the editor

**Left side: the MMS editor.**

* **Rows.** Use the toolbar or the right-click menu to insert, duplicate, remove, and move rows. You can also drag a row by its number. Keyboard: `Ctrl/Cmd+Enter` inserts a row, `Alt+↑/↓` moves the row, and `Enter`/`↑`/`↓` move between rows.
* **Sign sequence** (`maingloss`, `domarm`, `ndomarm`). While you type in a gloss cell, the *Signs* panel lists the matching dictionary signs. Click a sign to preview its video. Double click a sign, or press `↓` and then `Enter`, to insert it into the edited cell. `<HOLD>` is always available.
* **Timing.** The *Relative timing* checkbox chooses between `transition`/`duration` (relative) and `framestart`/`frameend` (absolute). The unused pair is greyed out. A file's mode is guessed when you load it.
* **Inflections.** Each body part is a subsection: Torso, Head, Shoulders, Dominant hand, and Non-dominant hand. You can hide a body part with the toolbar checkboxes. The x/y/z components of a parameter are collapsed into one cell (`x, y, z`) by default. Use ▸/▾ in the header, or *Expand/Collapse x/y/z*, to switch.
  * Empty cells are allowed: an inflection whose cells are all empty is skipped for that row, and its empty x/y/z triples default to identity values. Only the x, y and z of a single parameter must be either all filled or all empty.
  * When you type a value into an empty x/y/z triple, its other components are filled with identity values (0, or 1 for scales).
  * Right-click a cell to fill an inflection group with identity values, clear it, or copy it to all rows.
* **Validation.** Problems are highlighted in the table and listed below it. Click an item to jump to its cell. Examples: unknown signs, missing timing, partially filled groups, and `<HOLD>` in the first row.
* **Timeline.** Below the table, the timeline shows each row's time range. Main glosses and arm overrides are on separate tracks, and transitions are drawn as lines. The selected row is highlighted, and clicking a block selects its row. Percentage durations use each sign's original duration, which is read from the dictionary in the background. While a duration is still unknown, its block is dashed. A red playhead follows the generated video or the 3D preview.

**Right side: the result.** Both buttons send the current table to the server, which runs the MMS-Player in Blender. A progress bar shows the current phase: loading signs, building the animation, and rendering frame *n* of *N*. The full Blender log is available under *Log*, and the job can be cancelled.

* **Preview 3D** computes only the animation, without rendering a video, and plays it in real time on the 3D character in the *3D preview* tab. This takes a few seconds. Drag to orbit, right-drag to pan, and scroll to zoom. *Reset view* goes back to the point of view of the video camera. The played gloss is shown at the top.
* **Render video** renders the MP4 video, shown in the *Video* tab. Use it for the final result, once the 3D preview is satisfying.

Previous renders are listed below. *load MMS* puts the MMS that produced a render back into the editor, and *3D* plays its animation on the 3D character.

**Files.** *Open…* loads an MMS from the project folder or from the player's `MMS-examples` (examples are read-only, so saving one creates a copy). The other file buttons are *Save* (`Ctrl/Cmd+S`), *Download*, and *Import*. The browser keeps a draft of the current table, so reloading the page doesn't lose your work.

## Architecture

```
WebGUI/
  server.py                  command line entry point
  server_options.local.json  persisted server options (created at first start)
  mmsweb/
    app.py                   Flask routes
    options.py               load/save of the persisted server options
    schema.py                MMS column sections, x/y/z groups, fill (inflection) groups, identity values
    mms_io.py                CSV parsing/serialization
    dictionary.py            index of <dictionary>/<class>/trimmed/<NAME>.blend
    jobs.py                  background job queues, subprocess handling, progress state
    player.py                MMS-Player / Blender invocation and progress parsing
  blender_scripts/
    progress_hook.py         loaded before main.py; prints the frame being rendered
    gloss_durations.py       reads the original duration of signs from the dictionary
  templates/index.html       the page (rendered by the server)
  static/app.js, style.css   the client (plain JavaScript, no build step)
  static/viewer3d.js         the real-time 3D preview (ES module, using Three.js)
  static/vendor/three/       Three.js r169 (MIT license): core, GLTFLoader, OrbitControls
```

The 3D preview loads the character from the player's `assets/gloria-260813.glb`. Regenerate it with `tools/export_character_glb.py` (see the player's `Docs/DEVELOPERS.md`) when the template scene changes. The animation data is produced by the player option `--export-preview-json`. Its bone transforms are in the local space of the glTF joints, so the viewer assigns them directly, interpolating between frames.

The server runs Blender jobs in two queues. Generated videos go to the *render* queue. Sign previews, 3D previews, and duration lookups go to a separate *aux* queue, so they don't wait behind long renders.

Progress comes from the player's output. `progress_hook.py` registers a `render_pre` handler that prints `@@MMSWEB frame <cur> <start> <end>` for every rendered frame. The player's `--log-to-console` output marks the earlier phases.

### HTTP API

`GET /api` lists every endpoint with a description. The main ones:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/glosses` | All signs in the dictionary |
| POST | `/api/glosses/preview` `{id}` | Preview URL of a sign, or a job that renders it |
| POST | `/api/glosses/durations` `{ids}` | Original durations; unknown ones are computed in a job |
| GET | `/api/projects`, `/api/projects/<name>`, `/api/examples/<name>` | List and load MMS instances |
| PUT | `/api/projects/<name>` `{rows, extra_columns, overwrite}` | Save an MMS |
| POST | `/api/generate` `{name, rows, relative, options}` | Render a video (and its 3D animation data); returns a job |
| POST | `/api/preview3d` `{name, rows, relative, options}` | Compute only the 3D animation data; returns a job whose result has `anim_url` |
| GET | `/api/jobs/<id>[?log=1]` | Job status, phase, progress (0–1), result, log |
| POST | `/api/jobs/<id>/cancel` | Cancel a job |
| GET | `/api/renders` | Previous renders, with `anim_url` when the 3D animation data is available |
| GET | `/media/character.glb` | The 3D character |

## Known limitations

* The MMS file doesn't record whether it uses relative or absolute timing, so the editor guesses when loading: relative if any `duration` is set.
* There is no authentication. Bind to `127.0.0.1` (the default) unless the network is trusted.
