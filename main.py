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
from player.logging import logger
from player.logging import enable_log_to_stdout
from player import extract

from typing import List, Optional


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
        "--render-sentence", action="store_true", help="Render the sentence video."
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
    bpy.context.scene.camera = bpy.data.objects["Camera"]

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


def render_sentence(sentence_id: str, generated_root: Path, glue: Glue, arguments: argparse.Namespace) -> None:
    """Render the original sentence from the database.

    This function performs no inflection. Therefore, rendering is as straightforward as it can be.

    @param sentence_id: The id of the sentence to render.
    @param generated_root: The root path for the corpus database.
    @param glue: Glue object that is used to connect compile the final animation.
    @param arguments: Command-line arguments.
    """
    sentence_id = "Satz" + sentence_id.lstrip("0")
    animation_data = Path(generated_root).joinpath(
        "sentences", "trimmed", f"{sentence_id}.blend"
    )
    with bpy.data.libraries.load(str(animation_data)) as (data_from, data_to):
        data_to.actions = data_from.actions
    glue.create_new_fcurves(f"updated_{sentence_id}")
    glue.combine_animation("final_action", f"updated_{sentence_id}", 1)

    post_bake(
        armature_obj_name=glue.armature_obj_name,
        action_name=glue.action_name,
        mp4_path=arguments.export_mp4,
        bvh_path=arguments.export_bvh,
        fbx_path=arguments.export_fbx,
        blend_path=arguments.export_blend,
        render_size_pct=arguments.render_size_pct,
        render_size_x=arguments.res_x,
        render_size_y=arguments.res_y,
    )


def execute_pipeline(arguments: argparse.Namespace) -> None:
    """Execute the mms pipeline.

    What does this method do?
    1. Read a mms file
    2. Import the necessary gloss in the MMS file
    3. Attach the IK controller
    4. Run the animation production pipeline.
    """
    mms_file = arguments.source_mms_file
    generated_root = arguments.corpus_generated_directory
    sentence_id = Path(mms_file).stem

    # Read the MMS from the given MMS file.
    mms = MMSParser(mms_file, generated_root).parse()
    # Compose the MoCap file names and check for their availability
    mms.find_mocap_data_files()

    # During the comparison it is necessary for us to only compute the sentence.
    # Thus, the following block assures that we load the correct sentence animation
    # and render the animation.
    if arguments.render_sentence:
        glue = Glue(
            mms=mms,
            ignore_bone_list="./assets/ignorelist.json",
            src_blendfile="./assets/defaults.blend",
            action_name="final_action"
        )
        render_sentence(sentence_id, generated_root, glue, arguments)
        return  # Exit the function. Because we do not need to continue at all.

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

    # Remove all existing objects from the scene
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)

    # Iterate on MMS rows
    for gloss in mms.glosses:
        logger.info(f"Processing gloss {gloss}: {mms[gloss].path}")
        # TODO -- Path might not exist if the "gloss" is <HOLD>
        if not mms[gloss].path.exists():
            raise Exception(f"File '{mms[gloss].path}' not found for gloss {gloss}.")

        # TODO -- in case of HOLD, now we are essentially resampling the whole action of the previous gloss.
        #         We could optimize it with an ad-hoc branch that simply copies two times the last frame of the previous action.

        # Pass it through the ArmatureOperator class and prepare the animation for further
        # processing. Since we want to have the same number of frames as the source
        # sentence, we are resampling the animation frames.
        # The gloss animation data is loaded inside the ArmatureOperator constructor
        armature_operator = ArmatureOperator(mms[gloss])
        inflected_armature = armature_operator.copy_armature()
        if not arguments.ignore_gloss_duration:
            if arguments.use_relative_time:
                armature_operator.resample(mms[gloss].duration(), use_rel_time=True)
            else:
                armature_operator.resample(mms[gloss].timing(), use_rel_time=False)

        # We add the extra controllers to ensure that we will be able to modify the
        # animation down the pipeline.
        controller = Controller(inflected_armature, armature_operator.src_armature.name, ik_target_list, gloss[0])
        name = armature_operator.mms_line.output_name
        controller.setup_chain(
            source_armature=armature_operator.src_armature,
            target_armature=inflected_armature,
            output_name=name,
            mms_line=mms[gloss],
            without_inflection=arguments.without_inflection,
        )

        if not arguments.without_inflection:
            controller.execute(inflected_armature, mms[gloss])

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

    # Finally we merge individual signs to produce the final utterance of the full sentence.
    print("Merging inflected glosses into the final timeline...")
    glue = Glue(mms=mms,
                ignore_bone_list="./assets/ignorelist.json",
                src_blendfile="./assets/defaults.blend",
                action_name="final_action")
    # Since the animation data is essentially empty after initializing a new one,
    # it is necessary to create f-curves that match the source data.
    glue.create_new_fcurves()
    # Put all the inflected glosses/actions into a final timeline
    glue.merge_animation(use_rel_time=arguments.use_relative_time)

    # Finalize the scene and export as MP4, BVH, FBX, or binary blender scene
    post_bake(
        armature_obj_name=glue.armature_obj_name,
        action_name=glue.action_name,
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

    print("Realizing MMS... ")
    execute_pipeline(args)

    print("All done.")
