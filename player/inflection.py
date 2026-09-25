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
from typing import List

import bpy
import mathutils
from player import bpy_utils

from player.logging import logger
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
        idx: int,
        target_armature: bpy.types.Object,
        src_armature_name: str,
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
        self.__arm = target_armature
        self.__src_armature_name = src_armature_name
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
    def target_armature(self):
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
    def src_armature_name(self):
        return self.__src_armature_name

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
        target_bone = scene_objects[self.target_armature.name].pose.bones[self.target_bone]
        root_bone = scene_objects[self.target_armature.name].pose.bones[self.target_root]

        target_bone_from_dict = scene_objects[self.src_armature_name].pose.bones[self.target_bone]
        root_bone_from_dict = scene_objects[self.src_armature_name].pose.bones[self.target_root]
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
        cube.parent = self.target_armature
        cube.parent_type = "BONE"
        cube.parent_bone = self.target_root
        return cube

    def inflect(self, frame):
        # Get references to the bone to move and the root of the IK chain
        scene_objects = bpy.context.scene.objects

        # target_bone = scene_objects[self.armature.name].pose.bones[self.target_bone]
        # target_root = scene_objects[self.armature.name].pose.bones[self.target_root]
        target_bone = scene_objects[self.src_armature_name].pose.bones[self.target_bone]
        target_root = scene_objects[self.src_armature_name].pose.bones[self.target_root]

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
        target_bone = bpy.context.scene.objects[self.target_armature.name].pose.bones[self.target_bone]
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


class InflectionDirector:
    """Responsible for orchestrating the IK controller.

        With each IK motions, different bones are going to be affected. This module contains
        the necessary IK controllers for the skeleton.

        It has to do the following things:
        1. Store the reference to parent of the IK bone.
        2. Create an IK bone
        3. Store the forward motion of the IK bone.
        4. Bake it into IK.
        5. Apply the IK inflection on the IK bones.

    """

    def __init__(self,
                 target_armature: bpy.types.Object,
                 src_armature_name: str,
                 target_configs: List[IKTargetConfig],
                 idx: int) -> None:
        """Initialize Controller object.

        @param armature: The source armature to be inflected.
        @param dictionary_armature_name: The name of the armature in dictionary.
        @param ik_targets: The list of IK targets responsible for controlling the bones.
        @param idx: The progressive ID of the gloss in the sequence.
        """
        self.ik_targets: List[GenericTarget] = []
        # Dynamically compose the inflection targets that allow to perform the inflection.
        for target_config in target_configs:
            obj_class = globals()[target_config.target]  # looks the class up in the module's own namespace with no import needed.
            ik_target = obj_class(
                idx,
                target_armature=target_armature,
                src_armature_name=src_armature_name,
                dominance=target_config.dominance,
                target_bone=target_config.bone,
                target_root=target_config.root,
                inflection_type=target_config.itype,
                constraints=target_config.constraints,
            )
            self.ik_targets.append(ik_target)

    def setup_chain(self,
                    source_armature: bpy.types.Object,
                    target_armature: bpy.types.Object,
                    inflected_action_name: str,
                    mms_line: MMSLine,
                    without_inflection: bool = False):
        """Set up the armature skeleton for animation.

        @param source_armature: The source armature containing the signing animation
        @param target_armature: The target armature that contains the IK controller.
        @param output_name: The name of the inflected action.
        @param mms_line: The row of the corresponding gloss.
        @param without_inflection: This flag allows to disable the animation.

        Note:
            1. We copy the original animation from the source into the target.
            This redundancy prevents us from modifying the original animation.

            2. Once we copy the animation, we update the animation of corresponding
            IK controllers.
        """

        if source_armature.animation_data is None:
            raise Exception("Animation data missing in source armature object")

        if source_armature.animation_data.action is None:
            raise Exception("Action missing in source armature object")

        if target_armature.animation_data is None:
            raise Exception("Animation data missing in target armature object")

        if target_armature.animation_data.action is None:
            raise Exception("Action missing in target armature object")


        source_action = source_armature.animation_data.action
        start = int(source_action.frame_range[0])
        end = int(source_action.frame_range[1])
        # print(f"Source animation {action.name} range: {start} to {end}")
        # 1. Copy skeletal animation from the main action track to the "inflected" one
        # TODO --  check if it is really needed to switch to POSE mode and use operators at all.
        bpy_utils.select_object(target_armature)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.select_all(action="SELECT")
        new_action = bpy.data.actions.get(inflected_action_name)
        target_armature.animation_data.action = new_action
        bpy.context.object.animation_data.action = new_action
        bpy.context.scene.frame_set(start)
        # print("Baking the forward pose into the IK bones.")

        # Copies the bone rotations from the source armature to the target, inflected one
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            for bone in source_armature.pose.bones:
                tgt_bone = target_armature.pose.bones[bone.name]
                tgt_bone.matrix_basis = bone.matrix_basis.copy()
                tgt_bone.keyframe_insert("location", frame=frame)
                tgt_bone.keyframe_insert("rotation_euler", frame=frame)

        # This performs the "baking" of the animation into the given animation IK controller
        for frame in range(start, end + 1):
            bpy.context.scene.frame_set(frame)
            for obj in self.ik_targets:
                tgt_bone = target_armature.pose.bones[obj.target_bone]
                tgt_root = target_armature.pose.bones[obj.target_root]
                location = tgt_bone.head + (tgt_root.head - tgt_root.tail)
                rotation = tgt_bone.rotation_euler.to_quaternion()
                if not isinstance(obj, TrajectoryTarget):
                    continue
                elif isinstance(obj, RelativeLocRotTarget):
                    location = tgt_bone.tail + (tgt_root.head - tgt_root.tail)
                elif isinstance(obj, HeadRotTarget):
                    location = tgt_bone.tail + (tgt_root.head - tgt_root.tail)
                    rotation = (
                        tgt_root.matrix.to_quaternion().inverted()
                        @ tgt_bone.matrix.to_quaternion()
                    )
                obj.ctrl.location = tgt_root.matrix.inverted() @ location
                obj.ctrl.rotation_quaternion = rotation
                obj.ctrl.keyframe_insert("location", frame=frame)
                obj.ctrl.keyframe_insert("rotation_quaternion", frame=frame)

        bpy.ops.object.mode_set(mode="OBJECT")

        for bone in self.ik_targets:
            bone.add_constraints()
            if not without_inflection:
                bone.init_from_mms(mms_line)
        # TODO: When without inflection, avoid the baking and copying animation.
        #       Instead use the original animation. (Priority: Low)

    def execute(self, armature_obj: bpy.types.Object, mms_line: MMSLine):
        """Inflect the IK targets of a given MMSLine and bake the animation.

        @param armature: The target armature containing the IK targets.
        @param mms_line: The MMS table
        """

        bpy_utils.select_object(armature_obj)
        bpy.ops.object.mode_set(mode="POSE")

        action = bpy.data.actions.get(f"inflected_{mms_line.output_name}")  # TODO -- try to get out of here this action name composition
        bpy.context.object.animation_data.action = action
        start = int(action.frame_range[0])
        stop = int(action.frame_range[1])
        logger.info(f"Frame start: {start}, Frame End: {stop}")

        # Inflect each of the targets per frame.
        for frame in range(start, stop + 1):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bone in self.ik_targets:
                bone.inflect(frame)
            # break
        # return

        # Finally bake the animation
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.nla.bake(
            frame_start=start,
            frame_end=stop,
            step=1,
            only_selected=True,
            visual_keying=True,
            clear_constraints=False,
            use_current_action=True,
            bake_types={"POSE"},
        )
        bpy.ops.object.mode_set(mode="OBJECT")
