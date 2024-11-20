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

#
# Create Target for the targets for inflection of the bone.
#


from abc import ABC, abstractmethod
from collections import abc
from keyword import iskeyword

import bpy
import mathutils
from player import bpy_utils

from player.mms_parser import MMSLine


class Target(ABC):
    """Target is an object or a bone that controls the inflection.

    We are defining a protocol that every target should follow. It
    should have a way to inflect the armature and add constraints on the armature.
    """

    delta_r = mathutils.Matrix.Identity(4)
    delta_o = mathutils.Quaternion()
    delta_t = mathutils.Matrix.Identity(4)
    target_type = "empty"

    @abstractmethod
    def instantiate(self):
        """Create a bone or object to apply rotation."""

    @abstractmethod
    def inflect(self, frame: int):
        """Allow the inflection of the armature."""

    @abstractmethod
    def add_constraints(self):
        """Allow the inflection of the armature."""

    @abstractmethod
    def __repr__(self) -> str:
        """Representation of the Target."""

    @abstractmethod
    def init_from_mms(self, mms: MMSLine):
        """Initialize the property for the IK target."""


class GenericTarget(Target):
    """This is only responsible for initializing a target."""

    def __init__(
        self,
        idx: int, armature: bpy.types.Object,
        dictionary_name: str,
        dominance: str,
        target_bone: str,
        target_root: str,
        inflection_type: str,
        constraints: dict
    ):
        """

        :param idx: Position of the gloss in the sentence (>=0)
        :param armature: reference to the object of type 'ARMATURE'
        :param dominance: "dom" or "ndom"
        :param target_bone: The name of the bone to inflect
        :param target_root: The name of the bones relative to which all deltas are computed
        :param inflection_type: Type of inflection "hand", "torso", "shoulder", "head"
        :param constraints: Dictionary of constraints to be applied during inflections (See: controller_config.json)
        """
        self.__idx = idx
        self.__arm = armature
        self.__dictionary_armature = dictionary_name
        self.__dominance = dominance
        self.__target_bone = target_bone
        self.__target_root = target_root
        self.__inflection_type = inflection_type
        self.__constraints = constraints
        self.ctrl = None

    def instantiate(self):
        pass

    def inflect(self, frame: int):
        pass

    def __repr__(self) -> str:
        return "Generic Target"

    def add_constraints(self):
        pass

    def init_from_mms(self, mms: MMSLine):
        pass

    @property
    def armature(self):
        return self.__arm

    @property
    def dominance(self):
        return self.__dominance

    @property
    def target_bone(self):
        return self.__target_bone

    @property
    def target_root(self):
        return self.__target_root

    @property
    def inflection_type(self):
        return self.__inflection_type

    @property
    def constraints(self):
        return self.__constraints

    @property
    def dict_armature(self):
        return self.__dictionary_armature

    @property
    def idx(self):
        return self.__idx


class LocalRotationTarget(GenericTarget):
    """This is responsible for the rotation of the object.

    Only applies rotation delta relative to the parent bone.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def inflect(self, frame):
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()  # TODO -- is it really needed?!
        scene_objects = bpy.context.scene.objects
        target_bone = scene_objects[self.armature.name].pose.bones[self.target_bone]
        root_bone = scene_objects[self.armature.name].pose.bones[self.target_root]

        target_bone_from_dict = scene_objects[self.dict_armature].pose.bones[self.target_bone]
        root_bone_from_dict = scene_objects[self.dict_armature].pose.bones[self.target_root]
        if self.delta_o is not None:
            current_rot_rel_to = self.get_rotation_rel_to(target_bone_from_dict, root_bone_from_dict)
            new_rot_rel_to = self.delta_o @ current_rot_rel_to
            rotation = self.compute_rotation_rel_to(target_bone, root_bone, new_rot_rel_to)
            target_bone.rotation_euler = rotation.to_euler("ZXY")
        target_bone.keyframe_insert("rotation_euler", frame=frame)

    def __repr__(self) -> str:
        return f"Local Rotation Target for {self.target_bone}"

    def init_from_mms(self, mms):
        self.delta_o = mms.hand_orientation(self.dominance)

    @staticmethod
    def compute_rotation_rel_to(
            source_bone: bpy.types.PoseBone,
            relative_bone: bpy.types.PoseBone,
            rotation: mathutils.Quaternion) -> mathutils.Quaternion:
        """
        Compute the rotation of a bone, where the rotation is expressed relatively to another bone.

        :param source_bone: The bone on which we want to set the rotation
        :param relative_bone: The bone relative to which the rotation is expressed
        :param rotation: The new rotation value,
        :return: The rotation value that can be set as local rotation to the target bone.
        """
        # Local rotation of the target bone
        src_theta_c_local = source_bone.rotation_euler.to_quaternion()
        # Armature-space rotation of the target bone
        src_theta_c_arm = source_bone.matrix.to_quaternion()
        # Armature-space rotation of the relative-to bone
        src_theta_r_arm = relative_bone.matrix.to_quaternion()
        # The rotation that we can set as local rotation of the target bone
        # to orient it in the same orientation as the relative-to bone.
        src_theta_c_r_initial = (
            src_theta_c_local @ src_theta_c_arm.inverted() @ src_theta_r_arm
        )
        # The final rotation, in local space for the target bone.
        src_theta_c_r_rotated = src_theta_c_r_initial @ rotation
        return src_theta_c_r_rotated

    @staticmethod
    def get_rotation_rel_to(source_bone: bpy.types.PoseBone, relative_bone: bpy.types.PoseBone):
        """Computes the relative rotation between the active bone and reference bone."""
        src_theta_b_arm = source_bone.matrix.to_quaternion()
        src_theta_r_arm = relative_bone.matrix.to_quaternion()
        return src_theta_r_arm.inverted() @ src_theta_b_arm


class TrajectoryTarget(GenericTarget):
    """These use external objects to cause the inflection.

    Applies the inflection of the trajectory. The points are translated, rotated and scaled.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ctrl = self.instantiate()
        self.head = None

    def instantiate(self):
        bpy.ops.object.empty_add(
            type="CUBE", align="WORLD", location=(0, 0, 0), scale=(0.5, 0.5, 0.5)
        )
        cube = bpy.context.active_object
        cube.name = f"IK_CTRL_FOR_{self.target_bone}_{self.idx}"
        cube.rotation_mode = "QUATERNION"
        cube.parent = self.armature
        cube.parent_type = "BONE"
        cube.parent_bone = self.target_root
        return cube

    def inflect(self, frame):
        # Get references to the bone to move and the root of the IK chain
        scene_objects = bpy.context.scene.objects

        # target_bone = scene_objects[self.armature.name].pose.bones[self.target_bone]
        # target_root = scene_objects[self.armature.name].pose.bones[self.target_root]
        target_bone = scene_objects[self.dict_armature].pose.bones[self.target_bone]
        target_root = scene_objects[self.dict_armature].pose.bones[self.target_root]

        # The vector to shift back from the tail to the head of the IK root bone
        root_vector = target_root.head - target_root.tail

        if self.head is None:
            self.head = target_root.matrix.inverted() @ (target_bone.head + root_vector)

        location = mathutils.Matrix.Translation((self.head.x, self.head.y, self.head.z))
        location_inverse = mathutils.Matrix.Translation((-self.head.x, -self.head.y, -self.head.z))

        head = target_root.matrix.inverted() @ (target_bone.head + root_vector)

        self.ctrl.location = self.delta_t @ location @ self.delta_r @ location_inverse @ head
        self.ctrl.keyframe_insert("location", frame=frame)

    def __repr__(self) -> str:
        return f"Trajectory Target for {self.target_bone}"

    def add_constraints(self):
        target_bone = bpy.context.scene.objects[self.armature.name].pose.bones[self.target_bone]
        ik_constraint = target_bone.constraints.new("IK")
        ik_constraint.target = self.ctrl
        ik_constraint.use_tail = self.constraints.use_tail
        ik_constraint.chain_count = self.constraints.chain_count
        ik_constraint.use_rotation = self.constraints.use_rotation
        bpy.context.view_layer.update()

    def init_from_mms(self, mms):
        h_translation = mms.translation(self.dominance)
        h_rotation = mms.traj_rotation(self.dominance)
        h_scale = mms.scale(self.dominance)
        self.delta_r = h_rotation @ h_scale
        self.delta_t = h_translation


class RelativeLocRotTarget(TrajectoryTarget):
    """Allow to modify the relative location and rotation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def inflect(self, frame):
        self.ctrl.location = self.delta_t @ bpy.context.scene.objects[self.ctrl.name].location
        self.ctrl.keyframe_insert("location", frame=frame)
        self.ctrl.rotation_quaternion = self.ctrl.rotation_quaternion @ self.delta_o
        self.ctrl.keyframe_insert("rotation_quaternion", frame=frame)

    def __repr__(self) -> str:
        return f"Relative Location/Rotation Target for {self.target_bone}"

    def init_from_mms(self, mms):
        if self.inflection_type == "torso":
            self.delta_t = mms.torso_shift()
            self.delta_o = mms.torso_rot()
        elif self.inflection_type == "shoulder":
            self.delta_t = mms.shoulder_shift(self.dominance)


class HeadRotTarget(TrajectoryTarget):
    """Allow to modify the relative location and rotation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def inflect(self, frame):
        self.ctrl.rotation_quaternion = self.ctrl.rotation_quaternion @ self.delta_o
        self.ctrl.keyframe_insert("rotation_quaternion", frame=frame)

    def __repr__(self) -> str:
        return f"Relative Location/Rotation Target for {self.target_bone}"

    def init_from_mms(self, mms):
        self.delta_o = mms.head_rot()


class IKTargetConfig:
    """Configures the entire IK system based on an input json file.
    Allows to get values from a nested dictionary structure using a dot notation.

    Modified from FrozenJson (Fluent Python)
    """

    def __new__(cls, arg):
        if isinstance(arg, abc.Mapping):
            return super().__new__(cls)
        elif isinstance(arg, abc.MutableSequence):
            return [cls(item) for item in arg]
        else:
            return arg

    def __init__(self, mapping):
        self.__data = {}
        for key, value in mapping.items():
            if iskeyword(key):
                key += "_"
            self.__data[key] = value

    def __getattr__(self, name):
        if hasattr(self.__data, name):
            return getattr(self.__data, name)
        else:
            return IKTargetConfig(self.__data[name])

    @property
    def dict(self):
        return self.__data
