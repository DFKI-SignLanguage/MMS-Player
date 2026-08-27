#
# Use:
# cd ..
# make -f MMS-examples/GenerateExampleVideos.mk


ifndef BLENDER_EXE
$(error BLENDER_EXE variable is not set)
endif

ifndef DICTIONARY_DIR
$(error DICTIONARY_DIR variable is not set)
endif

FFMPEG_EXE ?= ffmpeg

# Gets the list of MMS files and replace the suffix to mp4 to generate the list of targets
MMS_FILES := $(wildcard MMS-examples/*.mms.csv)
OUT_VIDEO_FILES = $(subst .mms.csv,.mp4,$(MMS_FILES))
OUT_GIF_FILES = $(subst .mp4,.gif,$(OUT_VIDEO_FILES))

all: $(OUT_VIDEO_FILES) $(OUT_GIF_FILES)
	@echo $(OUT_VIDEO_FILES)


# Main rule to create a video from an MMS
%.mp4: %.mms.csv
	$(BLENDER_EXE) --background --python main.py -- --dictionary-dir "$(DICTIONARY_DIR)" --source-mms-file "$<" --use-relative-time --export-mp4 "$@" --render-size-pct 50 --log-to-console --gloss-panel

# Rule to create a half-resolution, 15fps animated GIF from a generated video
%.gif: %.mp4
	$(FFMPEG_EXE) -y -i "$<" -vf "fps=15,scale=iw/2:ih/2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" "$@"

clean:
	rm -f $(OUT_VIDEO_FILES) $(OUT_GIF_FILES)

touch:
	@touch Examples-MMS/*.mms.csv
