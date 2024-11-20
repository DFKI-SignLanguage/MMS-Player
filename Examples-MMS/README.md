# MMS and inflection examples

This directory contains a set of manually edited examples for testing the inflection routines.

The intention is to test the inflection parameters separately, but also in combinations that are potentially leading to conflicts or overlaps (E.g., torso and hand location simultaneously).

All the examples are manually edited using the `duration` and `transition` columns for timing information. See later for more details.


Example files finish with extensions `.mms.csv`, as reminder that they are conceptually mms files but can be edited as common CSV files.

There is a `GenerateExampleVideos.mk` makefile allowing the automate the generation of a video for each MMS in this folder.

```bash
cd ..
export BLENDER_EXE=/path/to/blender/binary/
export AVASAG_CORPUS_DIR=/path/to/animation/dictionaty/
make -f Examples-MMS/GenerateExampleVideos.mk
```

For each *.mms.csv file, a corresponding *.mp4 is created.
