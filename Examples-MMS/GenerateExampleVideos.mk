#
# Use:
# cd ..
# make -f Examples-MMS/GenerateExampleVideos.mk


ifndef BLENDER_EXE
$(error BLENDER_EXE variable is not set)
endif

ifndef AVASAG_CORPUS_DIR
$(error AVASAG_CORPUS_DIR variable is not set)
endif

# Gets the list of MMS files and replace the suffix to mp4 to generate the list of targets
MMS_FILES := $(wildcard Examples-MMS/*.mms.csv)
OUT_VIDEO_FILES = $(subst .mms.csv,.mp4,$(MMS_FILES))

all: $(OUT_VIDEO_FILES)


# Main rule to create a video from an MMS
%.mp4: %.mms.csv
	$(BLENDER_EXE) --background --python main.py -- --corpus-generated-directory "$(AVASAG_CORPUS_DIR)/generated/" --source-mms-file "$<" --use-relative-time --export-mp4 "$@" --render-size-pct 50 --log-to-console


touch:
	@touch Examples-MMS/*.mms.csv
