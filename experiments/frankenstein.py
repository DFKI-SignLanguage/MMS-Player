"""
How to frankenstein two skeletons?

There are three different combinations that is possible
1.  Everything is main gloss
        - It is simple playback of the animation

2. Either Dominant or Non-Dominant is different
        - Then either the dominant and non-dominant hand will be playing different animation.

3. Both are different.
        - In this case, there are three animations. This can be the superset of the frankenstein system
        as it compromises

Current Issues to be tackled
1. How to sample the animation into same length or duration? 
    - Take the shortest one or take the longest one
    - One sampling routine is necessary

2. Copying the animation
    - While copying only rotations can be copied. However it might affect the overall feel of the animation 
    because of the offset that is present throughout the chain.
"""
import bpy


def sample_and_copy(source_action, target_action, target_bones, samples): 
    # For each of the bone in the target bones, find the location of the 
    # f-curve
    print("Merging.")
    for bone in target_bones:
        data_path = f'pose.bones["{bone}"].rotation_euler'
        for idx in range(3):
            source_fcurve = source_action.fcurves.find(data_path, index=idx)
            target_fcurve = target_action.fcurves.find(data_path, index=idx)
            for frame_number, t in enumerate(samples):
                sampled_value = source_fcurve.evaluate(t)
                print(frame_number, sampled_value)
                target_fcurve.keyframe_points.insert(frame_number + 1, sampled_value)
            target_fcurve.update()

        data_path = f'pose.bones["{bone}"].location'
        for idx in range(3):
            source_fcurve = source_action.fcurves.find(data_path, index=idx)
            target_fcurve = target_action.fcurves.find(data_path, index=idx)
            for frame_number, t in enumerate(samples):
                sampled_value = source_fcurve.evaluate(t)
                print(frame_number, sampled_value)
                target_fcurve.keyframe_points.insert(frame_number + 1, sampled_value)
            target_fcurve.update()


    print("Done merging.")
    pass


def compute_timesteps(frame_range, sample_size):
    steps = []
    frame_start = int(frame_range[0])
    frame_end = int(frame_range[1])
    ratio = (frame_end - frame_start) / (sample_size - 1)
    steps = [frame_start + x * ratio for x in range(sample_size)]
    print(steps)
    return steps


def copy_animation_track(main_action, final_action):
    print("Initiating copy.")
    print("Main_action: ", main_action.name)
    print("Copying...")
    for source_fcurve in main_action.fcurves:
        target_fcurve = final_action.fcurves.new(
            source_fcurve.data_path, index=source_fcurve.array_index
        )
        # Copy, 1-by-1, all the keyframes
        for i, src_kfp in enumerate(source_fcurve.keyframe_points):
            # Co-ordinates of the control points, starts from 0.
            # For the first keyframe_point, co[0] = 1. Therefore, adjust for off-by-1 error
            target_fcurve.keyframe_points.insert(
                frame=src_kfp.co[0],
                value=src_kfp.co[1],
                options={"FAST"},
            )
        target_fcurve.update()

    print("Finished copying.")



def resurrect():
    config = {
        'dom_bones': [
            'Bone_R_Clavicle',
            'Bone_R_UpperArm', 'Bone_R_Forearm', 'Bone_R_Hand',
            'Bone_R_Finger0', 'Bone_R_Finger01', 'Bone_R_Finger02',
            'Bone_R_Finger1', 'Bone_R_Finger11', 'Bone_R_Finger12', 'Bone_R_Finger13',
            'Bone_R_Finger2', 'Bone_R_Finger21', 'Bone_R_Finger22', 'Bone_R_Finger23',
            'Bone_R_Finger3', 'Bone_R_Finger31', 'Bone_R_Finger32', 'Bone_R_Finger33',
            'Bone_R_Finger4', 'Bone_R_Finger41', 'Bone_R_Finger42', 'Bone_R_Finger43',
        ],
        'ndom_bones': ['Bone_L_UpperArm', 'Bone_L_Forearm', 'Bone_L_Hand'],
    }

    glosses = {
            "main_gloss": "ZUG",
            "dom_gloss": "INDEX",
            "ndom_gloss": None,
    }

    # Select the main gloss
    main = glosses["main_gloss"]
    main_skeleton = bpy.data.objects[main]

    # Selet the dominant gloss
    dominant = glosses["dom_gloss"]
    dom_skeleton = bpy.data.objects[dominant]

    bones = config["dom_bones"]

    # Main skeleton action
    main_action = main_skeleton.animation_data.action
    end = int(main_action.frame_range[1])
    start = int(main_action.frame_range[0])
    sample_size = end - start + 1
    print("Sample size: ", sample_size)

    # Dominant action
    dom_action = dom_skeleton.animation_data.action

    samples = {
        main: compute_timesteps(main_action.frame_range, sample_size),
        dominant: compute_timesteps(dom_skeleton.animation_data.action.frame_range, sample_size)
    }
    
    animation_action = bpy.data.actions.get("frankenstein_action")
    if not animation_action:
        animation_action = bpy.data.actions.new("frankenstein_action")
        copy_animation_track(main_action, animation_action)
    else:
        print(animation_action.name)


    # Select the dominant gloss
    sample_and_copy(dom_action, animation_action, bones, samples[glosses['dom_gloss']])



resurrect()
