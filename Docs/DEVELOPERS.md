# MMS Visualizer - developers docs

This document describes the software architecture and the main routines implementing the MMS visualizer.

The whole MMS visualizer is a set of Blender scripts. As such, it heavily relies on the bpy namespace.
The visualizer is meant to be executed by invoking Blender through a command line interface and providing the main entry point as parameter of the `--python` option.
For more details on how to invoke the visualizer and the available options, please read the man [README.md](../README.md) file first.

## General realization strategy

The main goal of the visualizer, given an input MMS, is to take the sequence of glosses specified in the MMS and compose a timeline with the inflected version of each gloss.
It requires to have each gloss stored in a separate blend file, and also to have a target character to animate.

From an abstract point of view, given the animation of a GLOSS, one inflection is performed by:

* dynamically creating an IK controller;
* baking the bone animation curves into the IK controller;
* programmatically editing the motion of the IK controller (translation offset, rotation offset, or more complex trajectory transformation, ...);
* baking the resulting IK animation back into the armature bone animation curves;
* removing all the temporary IK controller.

When realizing an MMS, such procedure must be applied to each row of the MMS, and for each inflection needed.
From a practical point of view, instead of creating and destroying IK controllers at each inflection, the process is optimized by first creating all IK controllers, and then applying the inflections to all of them.
In so doing, only one "baking" process per row is needed. 

Hence, in pseudo-code, the realization process on an MMS instance works like this (from main.execute_pipeline()):

```
Load the main Blender scene (main parameter of the blender command line invocation)
Load the target character (see assets)
Load the MMS (provided as parameter) using the MMSParser
Load the inflection configuration (using Configurator), which specifies what IK controllers have to be used (and how) to perform an inflection.
For each row/gloss of the MMS:
  Load the GLOSS animation into an action
  Resample the GLOSS duration according to the timing information (ArmatureOperator.resample())
  Instantiate all the IK controllers needed to perform inflections (Controller.setup_chain())
  Apply the inflections to all IK controllers (Controller.execute())
    In turn, for ech frame of the animation, this invokes the target-specific inflection routine (Target.inflect()) 
  Prepare the new FCurves for the sequence composition (Glue.create_new_fcurves())
  Copy the inflected animation data into the main/final timeline (Glue.merge_animation())
  Finalize the scene (Glue.post_bake())
  If requested, export the final result as FBX, Blender file, MP4 render, animation data (also in Glue.post_bake())  
```

The core of the inflection is performed by subclasses of the Target abstract class.

**TODO** _Actually, "Inflector" would be a more appropriate name. Might change in the future._

A Target subclass know how to inflect something by providing a concrete implementation of the `.inflect()` method.
We refer to concrete subclasses of Target as "inflection strategies", i.e., how to perform an inflection. A strategy is a generic way of inflecting, and can be reused for several body parts.

At the moment, the Target hierarchy is as follows (see targets.py):

```
Target(ABC)                 - The top level abstract interface
  GenericTarget             - Abstract interface implementation, adding fields for all useful data
    LocalRotationTarget     - The simplest of all inflection strategies, adding only a delta to the local relative rotation. Doesn't use IK controllers.
    RelativeLocRotTarget    - Applies a delta translation and rotation to an IK controller. The delta values are relative to a given root, which is also the root of IK chain.
    HeadRotTarget           - (Subject to change, would better be RelativeRotTarget) Applies a delta rotation to an IK controller. The delta value is relative to a given root, which is also the root of IK chain.
    TrajectoryTarget        - The most complex of all inflections. Applies a full 3D rigid transformation (translation, rotation, non-uniform scaling) to all points of the trajectory of an IK controller.
```

There is a configuration file (see later) describing what inflection strategy to use for what armature bones.
At the moment, the relationship between the MMS columns and the inflections Targets is as follows:

| MMS column(s)                          | Target class         | controlled bone(s) | relative bone |
|----------------------------------------|----------------------|--------------------|---------------|
| (n)domhandrot                          | LocalRotationTarget  | Bone_(L)R_Hand     | Bone_Spine2   |
| (n)domhandrelocx/y/z/ax/ay/az/sx/sy/sz | TrajectoryTarget     | Bone_(L)R_Hand     | Bone_Spine2   |
| (n)domshoulderrelocx/y/z               | RelativeLocRotTarget | Bone_(L)R_Clavicle | Bone_Spine2   |
| torsorelocx/y/z/ax/ay/az               | RelativeLocRotTarget | Bone_Spine2        | Bone_Pelvis   |
| headrotx/y/z                           | HeadRotTarget        | Bone_Head          | Bone_Spine2   |

**TODO** _Future work includes adding translation ability to the head and probably removing rotation ability to the shoulders.
In addition, torso transformation might become relative to the hips,
and there might be a new dedicated inflection control for the hips._

## Files

These are the files implementing the visualizer:

```
main.py             - is the main entry point of the visualizer
serve.py            - is a Flask server used to process MMS files through a web REST API
player/             - the main package with all the modules needed by the player
  anim_utils.py     -
  ArmatureUtils.py  -
  bpy_utils.py      -
  controllers.py    - contrains the controller class, able to setup all the IK controllers and invoke the inflections on them
  extract.py        -
  merge.py          - all the classes/routines to compoise the sequence of (inflected) glosses on a single timeline
  mms_parser.py     - all the classes/routines able to parse an MMS csv file
  targets.py        - defines the hierachy of inflectino strategies
exporter/           - support scripts to export animation datra in a custom JSON format
  bone_list.py      - list of bones to be exported
  json_exporter.py  - a script to export bones rotation data into a JSON file
```

In addition, there are binary requirements:

```
assets/                         - binary files needed for the final blender scene
  avasag_avatar_casual.glb      - is our target character
  controller_config.json        - described what inflection strategy must be used for each target bone
  defaults.blend                - default blender scene, containing an imported version of the GLB. It contains some default rendering values and lights, and the timeline will be filled by the MMS animation.
  ignorelist.json               - list of bones that must be deleted after loading an armature
```

## Frames and duration of animations

Blender artists reason in terms of frames. In the MMS, time is means to be specified in seconds. This is also to decouple the MMS from technical aspects like the framerate used to record a sign or to generate a video.

While coding the MMS-Player this might lead to a bit of confusion. Let's clarify some concepts.

An animation, stored as BVH and loaded in Blender as an action, has a number of frames.
We define fs and fe as the starting and ending frames.
So, the number of frames `Nf = fe - fs + 1`.
The sampling rate `FPS` (usually 60 fps), let us define the time interval between frames `dt = 1 / FPS`, expressed in seconds.

The duration, in seconds, of an animation is thus `D = dt * (Nf - 1)`.
This because the last frame marks only the end of the animation, but doesn't define a duration in time.

Hence, when we want to multiply by a factor `k` the duration of an animation, we don't simply multiply the number of frames, but twe apply:

    Nf_new = (fe - fs) * k + 1

thus:

    D_new = dt * (fe - fs) * k

So, for example, with FPS=60 (dt = 0.01666), for an animation with fs=1 and fe=11 --> Nf = 11, D = 0.16666.
When scaling by a factor 3.0, we have Nf_new = 31 and D_new = 1.55 sec.

This reflects in the computation of the new durations when scaling animations duration is relative mode.

## Preparing the development environment

Highly recommended to use Linux or MacOS.

### Requisites

All you need to execute the code as non-developer (i.e., Blender and a Corpus directory), plus: 

* Python Version: 3.11.*
* Extra libraries: bpy (pip install bpy)


### Special notes for Ubuntu

The following instructions were used on Ubuntu 20.04 LTS (you should use the latest Ubuntu version instead, other debian based distros should also work well)


To do this on Linux, you might already have different Python versions that are also needed
You can Install a custom version of python like this:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11
```

from now on you can use python3.11 by using "python3.11" in the terminal. Also use it like this when you want to run this code.
you can map it to "python" or "python3" but do this at your own risk, as it might mess with your desktop manager or operating system. (After mapping it to "python3" I could not use my normal terminal app anymore)
If you want to map it to "python" (this worked for me):

```bash
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
sudo update-alternatives --config python
# then choose the version you want
```

Then install pip: (If you want to do this on your main system, you might want to use a virtual environment. Since we set this system up only to use this code, we skip this)

```bash
# download the get pip script
curl -O https://bootstrap.pypa.io/get-pip.py
# run the script with python 3.11
python3.11 get-pip.py
# Check the version of pip to confirm it's tied to Python 3.11
python -m pip --version
# This should output something like:
> pip 23.0 (python 3.12)
# now use pip to install bpy
python3.11 -m pip install bpy==4.2.0
```

For the Web server:

    pip install Flask==3.0.3

At this point you might get a warning that certain scripts are installed in a directory that is not on PATH, then you can fix that:

```bash
nano ~/.bashrc
```

add the following to the end of the opened file:

    export PATH="$HOME/.local/bin:$PATH"

then close it with "shift+X" and save the changes with "y"

Apply the changes:

```bash
source ~/.bashrc
```
verify the changes with:

```bash
echo $PATH
```
