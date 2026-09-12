"""The operators, which are thin: every decision is in the modules they call."""

import bpy
from bpy.props import BoolProperty, EnumProperty

from . import bake as bake_module
from . import build


def _pool(context, scope):
    if scope == "SELECTED" and context.selected_objects:
        chosen = set(context.selected_objects)
        # A joint is only useful with its bodies, and selecting a joint without
        # them is the likeliest thing a user does, so the selection is widened
        # to whatever it is attached to rather than reported as incomplete.
        for obj in list(chosen):
            if obj.parent is not None:
                chosen.add(obj.parent)
            chosen.update(obj.children)
            if obj.parent is not None:
                chosen.update(obj.parent.children)
        return list(chosen)
    return list(context.scene.objects)


class Scoped:
    """Shared ``scope`` property, so every operator offers the same choice."""

    scope: EnumProperty(
        name="Apply to",
        items=[
            ("SCENE", "Whole scene", "Every joint in the scene"),
            ("SELECTED", "Selection", "Only the selected joints and what they join"),
        ],
        default="SCENE",
    )


class SKHK_OT_build_constraints(Scoped, bpy.types.Operator):
    """Build Blender rigid body constraints from the Havok properties"""

    bl_idname = "skhk.build_constraints"
    bl_label = "Build Rigid Body Constraints"
    bl_options = {"REGISTER", "UNDO"}

    dynamic: BoolProperty(
        name="Simulate immediately",
        description=("Make the bodies active rather than passive. A Skyrim body is "
                     "parented to a bone and Blender's parenting overrides the "
                     "simulation, so leave this off until the bodies are unparented"),
        default=False,
    )

    def execute(self, context):
        result = build.build_rigid_body_constraints(
            context.scene, _pool(context, self.scope), self.dynamic)

        for problem in result.problems[:5]:
            self.report({"WARNING"}, problem)

        if result.built == 0:
            self.report({"WARNING"}, "No joints built (%s)" % result)
            return {"CANCELLED"}

        self.report({"INFO"}, "Built %s" % result)
        return {"FINISHED"}


class SKHK_OT_clear_constraints(Scoped, bpy.types.Operator):
    """Remove the rigid body constraints, leaving the Havok properties alone"""

    bl_idname = "skhk.clear_constraints"
    bl_label = "Clear Rigid Body Constraints"
    bl_options = {"REGISTER", "UNDO"}

    remove_bodies: BoolProperty(
        name="Remove rigid bodies too",
        description="Also remove the rigid bodies this add-on created",
        default=True,
    )

    def execute(self, context):
        removed = build.clear_rigid_body_constraints(
            context.scene, _pool(context, self.scope), self.remove_bodies)
        self.report({"INFO"}, "Removed %d constraint%s" % (removed, "" if removed == 1 else "s"))
        return {"FINISHED"}


class SKHK_OT_build_bone_limits(Scoped, bpy.types.Operator):
    """Put the joint limits on the pose bones, for posing rather than physics"""

    bl_idname = "skhk.build_bone_limits"
    bl_label = "Build Bone Limits"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        result = build.build_bone_limits(_pool(context, self.scope))

        for problem in result.problems[:5]:
            self.report({"WARNING"}, problem)

        if result.built == 0:
            self.report({"WARNING"}, "No bone limits built (%s)" % result)
            return {"CANCELLED"}

        self.report({"INFO"}, "Limited %d bone%s" % (result.built, "" if result.built == 1 else "s"))
        return {"FINISHED"}


class SKHK_OT_clear_bone_limits(Scoped, bpy.types.Operator):
    """Remove the bone limits this add-on added"""

    bl_idname = "skhk.clear_bone_limits"
    bl_label = "Clear Bone Limits"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = build.clear_bone_limits(_pool(context, self.scope))
        self.report({"INFO"}, "Removed %d limit%s" % (removed, "" if removed == 1 else "s"))
        return {"FINISHED"}


class SKHK_OT_bake(Scoped, bpy.types.Operator):
    """Write edited constraints back into the properties, ready to export"""

    bl_idname = "skhk.bake"
    bl_label = "Bake Constraints to Properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        result = bake_module.bake(_pool(context, self.scope))

        for problem in result.problems[:5]:
            self.report({"WARNING"}, problem)

        self.report({"INFO"}, "Baked: %s" % result)
        return {"FINISHED"}


CLASSES = (
    SKHK_OT_build_constraints,
    SKHK_OT_clear_constraints,
    SKHK_OT_build_bone_limits,
    SKHK_OT_clear_bone_limits,
    SKHK_OT_bake,
)
