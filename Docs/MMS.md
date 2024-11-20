# The MultiModal Signstream (MMS)

## What is an MMS

An MMS file is a sequence of signs described in a table.

Here is an example of the sign NICHT repeated three times: the first time neutral (as recorded), the second time as you were "whispering", and the third time as you were "screaming".

| maingloss | framestart | frameend | duration | transition | domgloss | ndomgloss | torsorelocx | torsorelocy | torsorelocz | torsorelocax | torsorelocay | torsorelocaz | domhandrelocx | domhandrelocy | domhandrelocz | domhandrelocax | domhandrelocay | domhandrelocaz | domhandrelocsx | domhandrelocsy | domhandrelocsz | ndomhandrelocx | ndomhandrelocy | ndomhandrelocz | ndomhandrelocax | ndomhandrelocay | ndomhandrelocaz | ndomhandrelocsx | ndomhandrelocsy | ndomhandrelocsz | headrotx | headroty | headrotz |
|-----------|------------|----------|----------|------------|----------|-----------|-------------|-------------|-------------|--------------|--------------|--------------|---------------|---------------|---------------|----------------|----------------|----------------|----------------|----------------|----------------|----------------|----------------|----------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|----------|----------|----------|
| NICHT     | 0          | 0        | 0.5      | 0.5        |          |           | 0           | 0           | 0           | 0            | 0            | 0            | 0             | 0             | 0             | 0              | 0              | 0              | 1              | 1              | 1              | 0              | 0              | 0              | 0               | 0               | 0               | 1               | 1               | 1               | 0        | 0        | 0        |
| NICHT     | 0          | 0        | 0.5      | 0.5        |          |           | -10         | 0           | 0           | 0            | 0            | 0.55         | 0             | 15            | 0             | 0              | 0              | 0              | 0.4            | 0.4            | 0.4            | 0              | 15             | 0              | 0               | 0               | 0               | 0.4             | 0.4             | 0.4             | 0        | 0        | -0.55    |
| NICHT     | 0          | 0        | 0.5      | 0.5        |          |           | 5           | 0           | 0           | 0            | 0            | -0.2         | 0             | 15            | 0             | 0              | 0              | 0              | 1.5            | 1.5            | 1.5            | 0              | 15             | 0              | 0               | 0               | 0               | 1.5             | 1.5             | 1.5             | 0        | 0        | 0.2      |

Each row of the MMS table is a sign.
Column describes which sign must be played back and other information on HOW it has to be played back.
In the previous example, in the first row, no transformation is applied, because the inflection vlues are left at the "identity transformation".
In the second and third instance, the sign is "inflected" by moving the position of the hand trajectory, shrinking or expanding the same trajectory, and inclining the torso and the head.

Tha basic philosophy of the MMS is:

1. At best, signs are realized by playing back full-body motion capture data;
2. If modifications ("inflections") are needed: load the animation, apply the minimal amount of needed on-the-fly motion editing, playback, throw away.

In the remainder of this document, all the aspect of the MMS will be explained.


## Basic structure

The first columns define basic information, like:

* the identifier of the sign to be played;
* the duration/speed of th sign playback;
* the transition time between the previous sign and the current one;
* if the sign has to be played on the full body, or the arms must execute another sign.

The remaining columns specify the "geometrical inflections" that can be applied to a sign.
For example, when the motion of the hands has to be relocated, the head titled, the shoulders shrugged.

The main difficulty in manually editing the inflection parameter values, is that they all expressed as numerical values driving geometrical transformations of the human body motion.
Hence, you won't see easy-to-express directives like "hand-location: a-bit-right", but rather express an offset in centimeters.

This gives much more power to the system, which works in a very flexible continuous space (rather than on a set of closed choices), but make it more difficult to be edited by hand.
In fact, ideally the MMS has been architected to be machine-readable and writable (for automated translation systems) or edited through the use of ad-hoc graphical user interfaces.
However, for testing purposes, some manual editing is still possible and rather understandable.


**A note on missing vs. empty cells.**

Each inflection has its own "Identity value". From math, the identity value of an operation, is the value that, applied to that operation, gives the same result of the initial value.
For math operations +  and *, 0 and 1 are the identity values (5 + 0 = 5; 5 * 1 = 5).

The same applies for inflections. For example, the hand relocation: for translation and rotation, the identity value is 0. For scaling, the identity value is 1.
However, there is a fundamental difference between filling MMS cells with identity values and leaving the cells empty.

For example:

| maingloss | framestart | frameend | duration | transition | domgloss | ndomgloss | domhandrelocx | domhandrelocy | domhandrelocz | domhandrelocax | domhandrelocay | domhandrelocaz | domhandrelocsx | domhandrelocsy | domhandrelocsz | domhandrotx | domhandroty | domhandrotz | ndomhandrelocx | ndomhandrelocy | ndomhandrelocz | ndomhandrelocax | ndomhandrelocay | ndomhandrelocaz | ndomhandrelocsx | ndomhandrelocsy | ndomhandrelocsz | ndomhandrotx | ndomhandroty | ndomhandrotz | 
|-----------|------------|----------|----------|------------|----------|-----------|---------------|---------------|---------------|----------------|----------------|----------------|----------------|----------------|----------------|-------------|-------------|-------------|----------------|----------------|----------------|-----------------|-----------------|-----------------|-----------------|-----------------|-----------------|--------------|--------------|--------------|
| INDEX     | 0          | 0        | 0.2      | 0          |          |           | 0             | 0             | 0             | 0              | 0              | 0              | 1              | 1              | 1              | 0           | 0           | 0           | 0              | 0              | 0              | 0               | 0               | 0               | 1               | 1               | 1               | 0            | 0            | 0            |
| INDEX     | 0          | 0        | 0.2      | 0.5        |          |           |               |               |               |                |                |                |                |                |                |             |             |             |                |                |                |                 |                 |                 |                 |                 |                 |              |              |              |

The previous MMS executes the sign INDEX two times.
The first row specifies identity values for trajectory transformation and for local hand rotation, for both hands.
The second row, leaves all the cells empty.
Conceptually, the result is the same. However, there are two major differences.

First: performances. If the cells are empty, the corresponding routines that are supposed to perform the inflections are simply skipped. This results in an increase of performances and thus reduced generation time.

Second: potential numerical errors. Inflection routines are composed of several stages (see developer docs for details). In general, each inflection requires to read the rotation values of the skeleton and use it to animate IK controllers, alter the animation values of the IK controllers, and write the resulting rotation values back into the skeleton.
Each of those stages might introduce numerical approximation, not to talk about the (back)-conversion between euler angles and quaternions, and the fact that an IK solver might introduce some offsets (e.g., at the elbow).

In summary, computing inflection using identity values wastes computation time, and might introduce unwanted glitches.
If an inflection is not really needed, simply skip it.

Please, notice that inflection columns pertaining to the same inflection group, must all be filled qwith values, or all left empty.
For example, if you only want to relocate/translate the dominant hand with domhandrelocx/y/z: sorry, but the other 6 columns /ax/ay/az/sx/sy/sz must be also filled, with identity values.


##  How to edit an MMS

It follows a column-by-column description of the MMS format.


### Main GLOSS: maingloss

This specifies the ID of the main gloss to play back on the full body of the avatar.
It is an arbitrary string, to be interpreted as Gloss-ID, and the corresponding animation data must be present in the sign dictionary in order to be played back properly.

The **\<HOLD>** gloss.

There is a special gloss called `<HOLD>`, which implements a pause in the sign execution.
This is a well known phenomenon of every sign language.

If the `<HOLD>` Gloss-ID is found in the `maingloss` columns, the avatar "freezes" for the specified amount of time, retaining the position of the full body reached at the end of the previous sign.


### Timestamps: framestart/end

Imagining a timeline, where every gloss would be put in a sequence, this two columns specify the moment on the timeline (in seconds) where the sign starts and ends its execution.
Row-by-row, these timestamps are supposed to increase with respect to the previous sign, and the end being bigger than the start, otherwise results are unpredictable.

* `framestart` in seconds, defines the position on the timeline to start the sign playback;
* `frameend` in seconds, defines the position on the timeline for the last frame. 

Every sign has its "nominal" duration (as it was recorded), if the difference between end and start differs from the original sign duration, the playback will be accelerated or slowed down.


### Alternative timestamps: duration, transition

This two columns represent an alternative way to express the timeline of the sign sequence.
Instead of specifying timestamps on an absolute scale, one can express them on a relative fashion.

* `duration` in seconds, says how long must be the playback of a sign.
  * a plain number indicates the duration is seconds;
  * a number followed by % indicates an acceleration or slowdown of the sign execution.
* `transition` in seconds, says how much to wait from the end of the execution of the previous sign;
  * if the row is the first in the table, it simply defines an initial delay before starting the execution of the sequence.

This method of defining the timeline might be (for some cases) less machine friendly, but much more human friendly when composing MMS instances by hand.

Whether this two columns are used, or the absolute values (framestart/end), is specified in one option of the main MMS visualizer (`--use-relative-time`).
This also means that the two methods (absolute or relative) can not be mixed. If these two columns are used, the other two are completely ignored (and vice versa).


### GLOSS for (Non-)dominant hand: (n)domgloss

While the `maingloss` column specifies the sign that is played back on the whole body, it is possible also to override the animation of the left and right arms with animation data from another signs.

* `domglss` says from which sign to take the data to animate the dominant arm (from the shoulder to the fingertips);
* `ndomgloss` is the same for the non-dominant arm.

In fact, when both `domgloss` and `ndomgloss` columns are specified, we are playing back animation data from three signs simultaneously.


### Hands trajectory: (n)domhandrelocx/y/z/ax/ay/az/sx/sy/sz

Rigid 3D transformation applied to the points of the trajectories of the hands. 

For each hand, you must specify _simultaneously_ ALL the NINE following columns. For dominant hand:

* For the translation of the trajectory (in cm): `domhandrelocx`, `domhandrelocy`, `domhandrelocz`.
* For the rotation of the trajectory around its starting point (angles in radians): `domhandrelocax`, `domhandrelocay`, `domhandrelocaz`.
* For the scaling of the trajectory around its starting point (unit-less multipliers): `domhandrelocsx`, `domhandrelocsy`, `domhandrelocsz`.

And similarly, another six to control the trajectory of the non-dominant hand (use `ndom` as prefix).

The transformation of the trajectory of the hand is relative to torso bone `Bone Spine2`. Hence:

* +x towards the back of the interpreter
* +y up
* +z towards the left of interpreter


### Hands rotation: (n)domhandrotx/y/z

Delta rotation applied to the hand bone.
You must specify one of both of the following column set:

* For the dominant hand (in radians): `domhandrotx`, `domhandroty`, `domhandrotz`.
* For the non-dominant (in radians): `ndomhandrotx`, `ndomhandroty`, `ndomhandrotz`. 

Rotation is relative to torso (`Bone Spine2`). So uses the same axes as in (n)domhandreloc.


### Head rotation: headrotx/y/z

Deltas to the rotation of the head. It is applied to an IK controller influencing head and neck bones.

You must specify simultaneously all the three columns: `headrotx`, `headroty`, `headrotz`.

Rotation is relative to torso (`Bone Spine2`). So uses the same axes as in (n)domhandreloc.


### Shoulders: (n)domshoulderrelocx/y/z

Add a delta offset to the animation of the shoulders.

You must specify simultaneously all the six columns: `domshoulderrelocx`, `domshoulderrelocy`, `domshoulderrelocz`, `ndomshoulderrelocx`, `ndomshoulderrelocy`, `ndomshoulderrelocz`.

This is implemented by applying the offset to an IK controller relative to torso bone `Bone Spine2`.
Hence, the offset directions are:

* +x towards the back of the interpreter
* +y up 
* +z towards the left of interpreter

E.g.: negative X values make the avatar crouch, while positive Y values make the avatar shrug.


### Torso: torsorelocx/y/z/ax/ay/az

Deltas for location and rotation of torso. It is applied to an IK controller influencing bone `Bone Spine2` and down for three spine bones.
(Maybe will need to be relative to hips in future work).

You must specify simultaneously all the 6 columns:
`torsorelocx`, `torsorelocy`, `torsorelocz`, `torsorelocax`, `torsorelocay`, `torsorelocaz`.


Transformation relative to `Bone Pelvis`:

* +x towards the back of the interpreter
* +y up
* +z towards the left of interpreter
