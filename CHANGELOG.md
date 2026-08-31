# Changelog

MMS-Player Changelog.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [Unreleased]

- Simplified action management. Now supporting dictionary versions with purged Blender scenes (Dictionary size reduced to less than 5%. See Dictionary deploy of 260828)
- Creation of MMS Examples: Added exit code 1 to Blender, to better manage errors druring make invokes.

## [0.3.0] - 2025-08-27

- Important fix to support GLOSSES with a dash (-) in their name.
- main.py can now be invoked also from another directory: `player` module and `assets` are searched locally.
- Important option changed `--corpus-generated-directory` --> `--dictionary-dir`.
- Added (optional) subtitles showing the currently played GLOSS or transition.
- Restored basic REST server and added sample client.

## [0.2.0] - 2025-08-18

- Updated backend Gloria avatar with ARKit-compatible blendshapes.
- Facial animation supported! (Requires a new dictionary download)
- Hips are now animated!
- Tested with Blender LTS 4.2.23 (solves some render glitches in the shadows).
- Added example videso to the docs.

## [0.1.0] - 2025-05-13

### Added

- This was the first public release after cleanup of private code. Released together with the pubication at the SLTAT 2025 workshop on Sign Language Translation and Avatar Technologies.
- Refactoring and cleanups with respect to the original thesis implementation.
- Fully body animation.
- All inflection routines for the body impelemented.
- Fixed management of timing in both absolute and relative forms.
