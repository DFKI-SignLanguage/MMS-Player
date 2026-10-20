# Changelog

MMS-Player Changelog.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [Unreleased]

- Issue #28. Inflections are now selected row by row: leaving the cells of an inflection group empty in a row means that the group is not applied to that row (no IK controllers are created), even if other rows use it. Rows with no inflection at all skip the IK baking.
- Within an inflection group used in a row, empty x/y/z triples default to identity values (e.g., only `domhandrelocx/y/z` can be filled, without `domhandreloca*`/`domhandrelocs*`). A triple with only some of x/y/z filled is reported as an error.
- Fix: dominant and non-dominant shoulder relocations (`domshoulderreloc*`, `ndomshoulderreloc*`) can now be specified independently.
- Renamed and adjusted the Makefile for the MMS-Examples. Check `MMS-Examples/README.md` for details. 
- Implemented a WebGUI for easier editing and preview of MMS instances.
- New option `--export-preview-json` to export the realized animation (local bone transforms and facial blendshapes for every frame) for real-time playback, without rendering a video. See `player/preview_exporter.py`.
- New script `tools/export_character_glb.py` to export the character of the template scene into `assets/gloria-260813.glb`, for real-time playback.
- WebGUI: real-time 3D preview of the animation with Three.js (*Preview 3D* button and *3D preview* tab). Rendering the video is needed only for the final result. Videos rendered from the WebGUI can also be viewed in 3D.
- WebGUI: the single-sign dictionary preview is also in real-time 3D, with the same controls of the main preview. Videos are rendered only for full sentences. The `--preview-size-pct` server option was removed.
- Fix: the facial animation was not applied to the right eye (`Eye_R`) mesh.
- More human-friendly management of MMS inflection values. Now rotations are expressed in degrees and all numbers are rounded to 1 decimal.
- Issue #34. Fix: the avatar was sliding forward and backwards around a <HOLD>. `Bone_Root` (keyed by all glosses) is now in `assets/animated_bones.json`, so the hold action freezes it too, instead of resetting it to its rest location.

## [0.5.1] - 2026-10-14

- Major revision of the main MMS realization cycle:
  - eliminated action reference relying on their name.
  - moved management of maingloss HOLD into the main top-level cycle.
  - Realization of HOLD doesn't load the full animation anymore, but more quickly copied the last keyframe of the previous inflected animation.
- Fix: <HOLD> is now correctly freezing the pose of the inflected animation, not the imported one.
- It is not NOT possible anymore to specify a relative time duration (e.g., duration 60%) if the main gloss is <HOLD>.

## [0.5.0] - 2026-10-07

- Issue #8. "Frankenstein" feature: the new `domarm`/`ndomarm` columns (formerly documented as `domgloss`/`ndomgloss`) override the animation of the dominant/non-dominant arm with another gloss, or freeze it with `<HOLD>`. See Docs/MMS.md.
- Added option `--target-fps` to specify a target animation speed, independently from the framerate of the dictionary glosses. Will allow mixing dictionaries captured at different FPS. Need to update to dictionary `DictionaryGeneration-deploy-261001`, where the correct FPS is set in every gloss Blender scene.
- Removed old buggy options `--extract` and `--extract-path`
- Issue #15. Removed the option to render a full sentence. Can easily be realized by automatically computing an MMS with 1 row.
- Removed support for multiple `fa:`/`num:` glosses in a single MMS row (e.g., `num:1-2-3`). It was leading to too many code conditionals and arbitrary choices. Each gloss must now be on its own row.

## [0.4.0] - 2026-09-07

- Simplified action management. Now supporting dictionary versions with purged Blender scenes (Dictionary size reduced to less than 5%. Update to `DictionaryGeneration-deploy-260828`)
- Creation of MMS Examples: In examples creation, added `--python-exit-code 1` to Blender command line invokation, to correctly manage rule dependencies on failures.

## [0.3.0] - 2026-08-27

- Important fix to support GLOSSES with a dash (-) in their name.
- main.py can now be invoked also from another directory: `player` module and `assets` are searched locally.
- Important option changed `--corpus-generated-directory` --> `--dictionary-dir`.
- Added (optional) subtitles showing the currently played GLOSS or transition.
- Restored basic REST server and added sample client.

## [0.2.0] - 2026-08-18

- Updated backend Gloria avatar with ARKit-compatible blendshapes.
- Facial animation supported! (Requires a new dictionary download)
- Hips are now animated!
- Tested with Blender LTS 4.2.23 (solves some render glitches in the shadows).
- Added example videos (Animated GIFs) to the docs.

## [0.1.0] - 2025-05-13

### Added

- This was the first public release after cleanup of private code. Released together with the pubication at the SLTAT 2025 workshop on Sign Language Translation and Avatar Technologies.
- Refactoring and cleanups with respect to the original thesis implementation.
- Fully body animation.
- All inflection routines for the body impelemented.
- Fixed management of timing in both absolute and relative forms.
