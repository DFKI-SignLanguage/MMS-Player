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

import argparse
import json
import sys
import bpy
from pathlib import Path

# TODO -- this is needed to find the local module (player) when invoked through Blender. Try to find a better solution.
sys.path.append("./")

from player.mms_parser import MMSParser
from player.ArmatureUtils import ArmatureOperator
from player.merge import Glue
from player.controllers import Controller
from player.targets import IKTargetConfig
from player.bpy_utils import select_object
from player.logging import logger
from player.logging import enable_log_to_stdout
from player import extract

from typing import List, Optional


# The template Blender scene containing the character, the light setup, and some default rendering parameters
DEFAULT_BLEND_SCENE = "./assets/gloria-260624.blend"
# In the template scene, the name of the armature object to be animated.
TARGET_ARMATURE_NAME = "skeleton #5"
# In the template scene, the name of the face to be animated
TARGET_MESH_NAME = "gloria"
# In the template scene, the name of the camera object used for rendering.
RENDER_CAMERA_NAME = "Camera"
# The name of the final action containing the composed sign sequence
TARGET_ACTION_NAME = "final_action"
# The name of the final ShapeKeys action containing the composed sign sequence for the facial animation
TARGET_SHAPEKEYS_ACTION_NAME = "final_shapekeys_action"

# Path to the JSON file with the list of bones to ignore during animation procedures
# BONES_IGNORE_LIST_PATH = "./assets/ignorelist.json"


def add_options(arg_parser: argparse.ArgumentParser):
    """Add command line options to the parser.

    :param arg_parser: Argument parser

    Contains all the necessary flags and options for running the MMS Realization
    engine.
    """

    arg_parser.add_argument("--source-mms-file", type=str, required=True)

    arg_parser.add_argument("--corpus-generated-directory", type=str, required=True)

    arg_parser.add_argument(
        "--export-bvh",
        type=str,
        help="Exports the final merged sentence as animation into the given path.",
        required=False,
    )

    arg_parser.add_argument(
        "--export-fbx",
        type=str,
        help="Exports the final scene as fbx to the given path.",
        required=False,
    )

    arg_parser.add_argument(
        "--export-blend",
        type=str,
        help="Exports the final scene as blend to the given path.",
        required=False,
    )

    arg_parser.add_argument(
        "--export-mp4",
        type=str,
        help="Render the animation and save it to the path specified.",
        required=False,
    )

    arg_parser.add_argument(
        "--res-x",
        type=int,
        required=False,
        default=1080,
        help="Width of the rendered video.",
    )

    arg_parser.add_argument(
        "--res-y",
        type=int,
        required=False,
        default=1920,
        help="Height of the rendered video.",
    )

    arg_parser.add_argument(
        "--render-size-pct",
        type=int,
        required=False,
        default=100,
        help="The percentage of the target image size. Default keeps 100%% of the target resolution."
    )

    arg_parser.add_argument(
        "--without-inflection",
        action="store_true",
        help="By default, all the inflections are applied. "
        "Set this to true to disable inflections.",
    )

    arg_parser.add_argument(
        "--without-fingers",
        action="store_true",
        help="By default, all the fingers are used in evaluations."
        "Set this to true to disable the extraction of finger data.",
    )

    arg_parser.add_argument(
        "--extract",
        action="store_true",
        help="Allows extracting the motion data for evaluation.",
    )

    arg_parser.add_argument(
        "--use-relative-time",
        action="store_true",
        help="When specified, uses the `duration` and `transition` columns of the MMS"
             " (instead of the absolute framestart and frameend).",
    )

    arg_parser.add_argument(
        "--ignore-gloss-duration",
        action="store_true",
        help="When specified doesn't resample the animation (i.e., it uses the original duration of the gloss)."
             "It works only together with --use-relative-time and essentially forces the duration column to '100%'."
    )

    arg_parser.add_argument(
        "--extract-path",
        type=str,
        help="Path for final extraction result",
        default=None,
    )

    arg_parser.add_argument(
        "--render-sentence",
        type=int,
        help="Render the video of a si ngle specified sentence (AVASAG project)." \
        " Provide an integer number X as parameter, it will be converted in 'SatzX.blend" \
        "The file will be searched in the corpus in the folder 'generated/sentences/trimmed/'.",
        required=False
    )

    arg_parser.add_argument(
        "--log-to-console",
        action="store_true",
        help="If set, the log information will be also printed on the console. Handy for debugging purposes."
    )


def post_bake(
        armature_obj_name: str,
        action_name: str,
        render_size_x: int,
        render_size_y: int,
        mp4_path: Optional[str] = None,
        bvh_path: Optional[str] = None,
        fbx_path: Optional[str] = None,
        blend_path: Optional[str] = None,
        render_size_pct: int = 100,
):
    """Perform rendering and export.

    :param armature_obj_name: The name of the armature with the final animation.
    :param action_name: The name of the action with the final animation.
    :param mp4_path: Export path to render the final animation.
    :param bvh_path: Export path to store skeletal animation.
    :param fbx_path: Export path to store 3D animated asset
    :param blend_path: Export path to save the 3d scene
    :param render_size_pct: Percentage of the final render.
    :param render_size_x: Width of final render.
    :param render_size_y: Height of final render.
    """

    from player import bpy_utils

    # Hide the bones
    armature = bpy.data.objects[armature_obj_name]
    armature.hide_set(True)

    #
    # Set the render range
    frame_start = armature.animation_data.action.frame_range[0]
    frame_end = armature.animation_data.action.frame_range[1]
    bpy.context.scene.frame_start = int(frame_start)
    bpy.context.scene.frame_end = int(frame_end)

    #
    # Set the high quality render configuration
    # BLENDER_EEVEE_NEXT, BLENDER_WORKBENCH, CYCLES
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    # bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.eevee.taa_render_samples = 2
    bpy.context.scene.render.resolution_x = render_size_x
    bpy.context.scene.render.resolution_y = render_size_y
    bpy.context.scene.render.resolution_percentage = render_size_pct
    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.image_settings.file_format = "FFMPEG"
    # bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.ffmpeg.format = "MPEG4"
    bpy.context.scene.render.ffmpeg.codec = "H264"
    # bpy.context.scene.render.ffmpeg.constant_rate_factor = 'LOSSLESS'
    bpy.context.scene.render.ffmpeg.constant_rate_factor = "HIGH"

    #
    # Setup for the fast (Viewport) render configuration
    # bpy.context.space_data.shading.type = 'RENDERED'
    # bpy.context.space_data.region_3d.view_perspective = 'CAMERA'
    view3d = None
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            view3d = area
            break

    view3d.spaces[0].region_3d.view_perspective = "CAMERA"

    # Setup the objects to be rendered
    bpy.context.scene.camera = bpy.data.objects[RENDER_CAMERA_NAME]

    # Cleanup the animation curves
    action = bpy.data.actions.get(action_name)
    for fcurve in action.fcurves:
        for kfp in fcurve.keyframe_points:
            # Possible values: SINE, QUAD, CUBIC, QUART, QUINT
            kfp.interpolation = "SINE"
            # Easing in and out smoothens the curves horizontally on both sides.
            kfp.easing = "EASE_IN_OUT"

    with bpy.context.temp_override(area=view3d):
        bpy.ops.view3d.toggle_shading(type="RENDERED")

    # Render the VIDEO
    if mp4_path is not None:
        bpy.context.scene.render.filepath = mp4_path
        bpy.ops.render.render(animation=True)
        # bpy.app.handlers.load_post.append(render_opengl)
        print("Rendering done.")

    bpy_utils.select_object(armature)
    armature.hide_set(False)

    # Export the BVH
    if bvh_path:
        bpy.ops.export_anim.bvh(
            filepath=bvh_path,
            frame_start=int(frame_start),
            frame_end=int(frame_end),
            rotate_mode="ZXY",
        )  # Import with y-forward and z up

    # Export the FBX
    if fbx_path:
        bpy.ops.export_scene.fbx(
            filepath=fbx_path,
            object_types={"ARMATURE", "MESH"},
            bake_anim=True,
            bake_anim_use_all_bones=True,
        )  # Import with y-forward and z up

    bpy.context.scene.frame_set(1)
    armature.hide_set(True)

    if blend_path:
        print(f"Saving the blend file '{blend_path}'")
        blend_path = Path(blend_path)
        if not blend_path.is_absolute():
            blend_path = blend_path.absolute()

        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))


def initialize_scene():
    """Initialize the current Blender context:
    i) Copy all objects and worlds from the source template blender scene to the current context.
    ii) Link all objects into the current context to work on them.
    """

    # Select all objects and delete them.
    # Will leave only the armature data and the actions.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    # Load objects from the reference scene (nice character and lights)
    with bpy.data.libraries.load(DEFAULT_BLEND_SCENE) as (data_from, data_to):
        data_to.objects = data_from.objects
        data_to.worlds = data_from.worlds
    
    # Link all objects to the scene, to make them visible
    for obj in data_to.objects:
        bpy.context.scene.collection.objects.link(obj)

    # Set the current world to the first found in the loaded template
    bpy.context.scene.world = data_to.worlds[0]


def initialize_target_armature():
    """Replace the bone names in the rtemplate armature and create a new action.
    The original names in the template scene are "Bone Pelvis". This name doesn't work for the
    skeletal animations which are of format "Bone_Pelvis". Thus, we modify
    the name of bones in the original mesh itself as it is one time operation.

    Then, creates the final target action and assign it as current action of the armature
    """

    target_armature_obj = bpy.data.objects[TARGET_ARMATURE_NAME]
    assert isinstance(target_armature_obj, bpy.types.Object)
    assert target_armature_obj.type == "ARMATURE"

    for bone in target_armature_obj.pose.bones:
        bone.name = bone.name.replace(" ", "_")
        bone.rotation_mode = "ZXY"


def execute_single_sentence_realization_pipeline(arguments: argparse.Namespace) -> None:
    """
    For some use cases, it is necessary for us to only render the single original entence data into the avatar.
    Inflections are not needed
    Thus, the following block assures that we load the correct sentence animation render it, but bypassing the instancing and inflection overhead.
    This function performs no inflection. Therefore, rendering is as straightforward as it can be.
    """

    # Must be true otherwise this block is not called.
    assert arguments.render_sentence is not None

    sentence_id: int = arguments.render_sentence

    # Initialize the target scene and armature
    initialize_scene()
    initialize_target_armature()

    # Load the source animation data from the sentence file
    sentence_file = "Satz" + str(sentence_id) + ".blend"
    sentence_path = Path(arguments.corpus_generated_directory).joinpath(
        "sentences", "trimmed", sentence_file
    )

    # Import the sentence animation
    with bpy.data.libraries.load(str(sentence_path)) as (data_from, data_to):
        data_to.actions = data_from.actions

    glue = Glue(
        mms=None,  # It won't be needed when rendering a single sentence
        target_armature_obj_name=TARGET_ARMATURE_NAME,
        target_action_name=TARGET_ACTION_NAME
    )

    # Prepare the target animation curves, specifiyng the name of the source action
    # By manually specifying the source action, the mms is not needed.
    source_action_name = "updated_Satz" + str(sentence_id)
    glue.prepare_target_fcurves(source_action_name)
    glue.append_action(target_action_name="final_action", source_action_name=source_action_name, start=1)

    post_bake(
        armature_obj_name=glue.src_armature_obj_name,
        action_name=glue.target_action_name,
        mp4_path=arguments.export_mp4,
        bvh_path=arguments.export_bvh,
        fbx_path=arguments.export_fbx,
        blend_path=arguments.export_blend,
        render_size_pct=arguments.render_size_pct,
        render_size_x=arguments.res_x,
        render_size_y=arguments.res_y,
    )



def execute_mms_realization_pipeline(arguments: argparse.Namespace) -> None:
    """Execute the mms pipeline.

    What does this method do?
    1. Read a mms file.
    2. Import the necessary gloss in the MMS file.
    3. Attach the necessary IK controllers.
    4. Run the animation production pipeline.
    """
    mms_file = arguments.source_mms_file
    generated_root = arguments.corpus_generated_directory
    sentence_id = Path(mms_file).stem

    # Read the MMS from the given MMS file.
    mms = MMSParser(mms_file, generated_root).parse()
    # Compose the MoCap file names and check for their availability
    mms.ensure_mocap_data_files()

    for gloss in mms.glosses:
        mmsline = mms[gloss]
        assert mmsline.path is not None

    #
    # READ INFLECTION CONFIGURATION

    # Read the configuration from file and initialize the IK target.
    #     The configuration file consists of bone target and bone root for the IK
    #     controller. This file also details information on the constraints required
    #     for the IK controller.
    # The way items are added to the bone list defines the execution order for the
    # ik target.

    config_path = Path("./assets/controller_config.json")
    if not config_path.exists():
        raise Exception(f"The config '{config_path}' couldn't be located.")

    with open(config_path, "r") as stream:
        config_data = json.load(stream)

    ik_config = IKTargetConfig(config_data)
    ik_target_list: List[IKTargetConfig] = []

    if mms.inflections_availability_dict["torso"]:
        ik_target_list.append(ik_config.torso)
        print("Added Torso Inflector.")

    if mms.inflections_availability_dict["head"]:
        ik_target_list.append(ik_config.head)
        print("Added Head Inflector.")

    if mms.inflections_availability_dict["shoulders"]:
        ik_target_list.append(ik_config.shoulders.dom)
        ik_target_list.append(ik_config.shoulders.ndom)
        print("Added two Shoulder Inflectors")

    if mms.inflections_availability_dict["domhandreloc"]:
        ik_target_list.append(ik_config.hands.dom.loc)
        print("Added dominant hand trajectory inflector.")

    if mms.inflections_availability_dict["domhandrot"]:
        ik_target_list.append(ik_config.hands.dom.rot)
        print("Added dominant hand rotation inflector.")

    if mms.inflections_availability_dict["ndomhandreloc"]:
        ik_target_list.append(ik_config.hands.ndom.loc)
        print("Added non-dominant hand trajectory inflector.")

    if mms.inflections_availability_dict["ndomhandrot"]:
        ik_target_list.append(ik_config.hands.ndom.rot)
        print("Added non-dominant hand rotation inflector.")

    if arguments.without_inflection:
        ik_target_list = []

    # Log the mms file
    logger.info("==================================")
    logger.info("MMS File: %s", mms_file)
    logger.info(f"List of IK target configurations ({len(ik_target_list)}):")
    for ik_target in ik_target_list:
        logger.info("IK Target Config: %s", ik_target.dict)
    logger.info("==================================")

    # Remove all existing temporary objects from the scene
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)

    # Iterate on MMS rows
    # For each row, create a new action with the inflected gloss animation
    for gloss in mms.glosses:

        mmsline = mms[gloss]

        logger.info(f"Processing gloss {gloss} from file {mmsline.path}")

        # TODO -- Path might not exist if the "gloss" is <HOLD>
        assert mmsline.path is not None
        if not mmsline.path.exists():
            raise Exception(f"File '{mms[gloss].path}' not found for gloss {gloss}.")

        # TODO -- in case of HOLD, now we are essentially resampling the whole action of the previous gloss.
        #         We could optimize it with an ad-hoc branch that simply copies two times the last frame of the previous action.

        # Pass it through the ArmatureOperator class and prepare the animation for further
        # processing. Since we want to have the same number of frames as the source
        # sentence, we are resampling the animation frames.
        armature_operator = ArmatureOperator(mmsline)

        armature_operator.load_animation()

        # The source armature has been loaded
        assert armature_operator.src_armature is not None
        # Here the "imported_" actions have been created
        assert "imported_" + mmsline.output_name in bpy.data.actions
        assert "imported_blendshapes_" + mmsline.output_name in bpy.data.actions

        inflected_armature = armature_operator.copy_armature()

        # Inflected animation is already prepared while copying the armature.
        # TODO -- Postpone action creation.
        assert f"inflected_{mmsline.output_name}" in bpy.data.actions

        if not arguments.ignore_gloss_duration:
            if arguments.use_relative_time:
                armature_operator.resample(timing=mmsline.duration(), target_action_name="resampled_" + mmsline.output_name, use_rel_time=True)
                armature_operator.resample_blendshapes_action(timing=mmsline.duration(), use_rel_time=True, src_action_name="imported_blendshapes_" + mmsline.output_name, target_action_name="resampled_blendshapes_" + mmsline.output_name)
            else:
                armature_operator.resample(timing=mmsline.timing(), target_action_name="resampled_" + mmsline.output_name, use_rel_time=False)
                armature_operator.resample_blendshapes_action(timing=mmsline.duration(), use_rel_time=False, src_action_name="imported_blendshapes_" + mmsline.output_name, target_action_name="resampled_blendshapes_" + mmsline.output_name)

        # Here the "updated_" animation has been created
        assert "resampled_" + mmsline.output_name in bpy.data.actions

        # We add the extra controllers to ensure that we will be able to modify the animation down the pipeline.
        inflector = Controller(inflected_armature, armature_operator.src_armature.name, ik_target_list, gloss[0])
        inflector.setup_chain(
            source_armature=armature_operator.src_armature,
            target_armature=inflected_armature,
            inflected_action_name=f"inflected_{mmsline.output_name}",
            mms_line=mms[gloss],
            without_inflection=arguments.without_inflection,
        )

        # Here the target "inflected_..." action has been already created
        assert "inflected_" + mmsline.output_name in bpy.data.actions

        # Perform the inflection !!!
        if not arguments.without_inflection:
            inflector.execute(inflected_armature, mmsline)

    #
    # For each MMS line, the inflected action has been created
    for gloss in mms.glosses:
        mmsline = mms[gloss]
        # print("Expected inflected action presence ", "inflected_" + mmsline.output_name)
        assert "inflected_" + mmsline.output_name in bpy.data.actions
        assert "resampled_blendshapes_" + mmsline.output_name in bpy.data.actions

    #
    # Call the data extraction if requested
    if arguments.extract:
        print("Extracting the data to: ", arguments.extract_path)
        extract.run(
            mms,
            sentence_id,
            generated_root,
            arguments.extract_path,
            arguments.use_relative_time,
            arguments.without_fingers,
        )
        return

    # Load the template scene
    initialize_scene()

    # Checks
    assert TARGET_ARMATURE_NAME in bpy.context.scene.objects
    assert TARGET_ARMATURE_NAME in bpy.data.objects
    assert TARGET_MESH_NAME in bpy.context.scene.objects
    assert TARGET_MESH_NAME in bpy.data.objects

    # Check the types and fix the bone names of the target armature
    initialize_target_armature()

    #
    # Finally we merge individual signs to produce the final utterance of the full sentence.
    logger.info("Merging inflected glosses into the final timeline...")

    target_armature = bpy.data.objects[TARGET_ARMATURE_NAME]
    target_mesh = bpy.data.objects[TARGET_MESH_NAME]

    assert target_armature.type == 'ARMATURE'
    assert target_mesh.type == 'MESH'

    glue = Glue(
        mms=mms,
        target_armature_obj=target_armature,
        target_mesh_obj=target_mesh,
        target_action_name=TARGET_ACTION_NAME,
        target_shapekeys_action_name=TARGET_SHAPEKEYS_ACTION_NAME
    )

    # Since the animation data is empty after initializing a new one,
    # it is necessary to create f-curves that match the source data.

    # Take reference to the first gloss and their created actions.
    # They will be used as reference to create the fcurves in the target actions.
    gloss0 = mms.glosses[0]
    mmsline0 = mms[gloss0]

    ref_action = bpy.data.actions["inflected_" + mmsline0.output_name]
    ref_shapekeys_action = bpy.data.actions["resampled_blendshapes_" + mmsline0.output_name]

    glue.prepare_target_actions(reference_action=ref_action, reference_shapekeys_action=ref_shapekeys_action)

    assert TARGET_ACTION_NAME in bpy.data.actions
    assert bpy.context.scene.objects[TARGET_ARMATURE_NAME].animation_data is not None
    assert bpy.context.scene.objects[TARGET_ARMATURE_NAME].animation_data.action is not None
    assert bpy.context.scene.objects[TARGET_ARMATURE_NAME].animation_data.action.name == TARGET_ACTION_NAME

    select_object(bpy.data.objects[TARGET_ARMATURE_NAME])
    assert bpy.context.active_object.name == TARGET_ARMATURE_NAME
    # Also the referenced Armature instance has by default the same name,
    # but might have been renamed while loading the animation data from the other scenes.
    assert bpy.context.active_object.data.name.startswith(TARGET_ARMATURE_NAME), f"The name of the active object does not start with '{TARGET_ARMATURE_NAME}', but is '{bpy.context.active_object.data.name}'"

    # Prepare action and fcurves for the facial animation
    # Gather fcurves data from the first gloss
    # fcurves_info = gather_fcurves_info(action=bpy.data.actions["resampled_blendshapes_" + mmsline.output_name])
    # glue.prepare_target_action(new_action_name=TARGET_SHAPEKEYS_ACTION_NAME, curves_info=fcurves_info)

    assert TARGET_SHAPEKEYS_ACTION_NAME in bpy.data.actions

    #
    # Put all the inflected glosses/actions into a final timeline
    glue.realize_mms(use_rel_time=arguments.use_relative_time)

    # Finalize the scene and export as MP4, BVH, FBX, or binary blender scene
    post_bake(
        armature_obj_name=glue.armature_obj.name,
        action_name=glue.target_action.name,
        mp4_path=arguments.export_mp4,
        bvh_path=arguments.export_bvh,
        fbx_path=arguments.export_fbx,
        blend_path=arguments.export_blend,
        render_size_pct=arguments.render_size_pct,
        render_size_x=arguments.res_x,
        render_size_y=arguments.res_y,
    )


#
# MAIN
#
if __name__ == "__main__":
    argv = sys.argv

    if "--" in argv:
        # Used when the script is invoked from within Blender.
        print("Taking arguments after --...")
        argv = argv[argv.index("--") + 1:]
    else:
        # Used when the script is invoked from the command line.
        argv = argv[1:]

    print("Parsing arguments...")
    parser = argparse.ArgumentParser()
    add_options(parser)
    args = parser.parse_args(argv)

    if args.log_to_console:
        enable_log_to_stdout()

    if args.render_sentence:
        print(f"Realizing single sentence with numer {args.render_sentence} ...")
        execute_single_sentence_realization_pipeline(args)
    else:
        print(f"Realizing MMS from file '{args.source_mms_file}' ...")
        execute_mms_realization_pipeline(args)

    print("All done.")
