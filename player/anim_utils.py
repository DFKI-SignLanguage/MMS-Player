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

# Helper utility functions related to animation.

import bpy
from mathutils import Vector


def recenter_armature(armature_name, root_bone="Bone_Root"):
    """Recenter the armature bone.

    We have to recenter it so that it can prevent some sliding in the animation.
    In case of composing the animation using multiple glosses, there is slight,
    sliding.

    The recentering happens after application of the pose. Otherwise, there will
    be certain shift in the animation..
    """
    armature = bpy.data.objects[armature_name]
    armature.pose.bones[root_bone].location = Vector((0, 0, 0))
    # TODO: Verify that we can update the animation.


def copy_frame(source_armature, source_action, target_action, frame_id):
    """Copy the frame from given source action to a target action in the target armature."""
    # Get the bone name list from the source armature.
    bones = list(x.name for x in source_armature.pose.bones)
    print(bones)
    # The filter the bone data from the source for current frame.
    # Select the target action for the given target data.
    # Now copy each of the frame data from source to the target.
    # Make sure the transforms are now being completely copied.
    pass


def clear_ik_contstraint(armature, ik_bone):
    """Clear the constraint on the IK bone

    Clearing the constraint will allow the IK bone to have proper motion according to
    the forward kinematics
    """
    pass


def apply_ik_constraint(armature, ik_bone, target="HandIK"):
    """Apply the IK constraint.

    In order to move the IK bone according to the inflected trajectory, we will have
    to add contstraint to the IK bone. Doing this, we will be able to move the armature
    using `ik_bone`
    """
    bone = armature.pose.bones[ik_bone].bone
    pass


def apply_fk(armature, action):
    """Questionable method.

    TODO: Determine if this is relevant or not.
    """
    pass
