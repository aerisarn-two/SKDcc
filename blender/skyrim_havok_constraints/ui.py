"""One panel in the Physics properties tab."""

import bpy

from . import schema
from .joint import Joint, joints_in


class SKHK_PT_panel(bpy.types.Panel):
    bl_label = "Skyrim Havok Constraints"
    bl_idname = "SKHK_PT_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "physics"

    def draw(self, context):
        layout = self.layout
        joints = joints_in(context.scene.objects)

        box = layout.box()
        box.label(text="%d joint%s in the scene" % (len(joints), "" if len(joints) == 1 else "s"),
                  icon="CONSTRAINT")

        if joints:
            built = sum(1 for j in joints if j.rigid_body_constraint is not None)
            edited = sum(1 for j in joints
                         if j.rigid_body_constraint is not None
                         and j.get(schema.SIGNATURE, None) != _signature(j))
            box.label(text="%d built, %d edited since" % (built, edited))

        column = layout.column(align=True)
        column.label(text="Ragdoll (physics)")
        column.operator("skhk.build_constraints", icon="PHYSICS")
        column.operator("skhk.clear_constraints", icon="X")

        column = layout.column(align=True)
        column.label(text="Posing (no physics)")
        column.operator("skhk.build_bone_limits", icon="CON_ROTLIMIT")
        column.operator("skhk.clear_bone_limits", icon="X")

        column = layout.column(align=True)
        column.label(text="Before export")
        column.operator("skhk.bake", icon="EXPORT")


class SKHK_PT_joint(bpy.types.Panel):
    bl_label = "Havok Joint"
    bl_idname = "SKHK_PT_joint"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        from .joint import is_attachment_point
        return context.object is not None and is_attachment_point(context.object)

    def draw(self, context):
        layout = self.layout
        joint = Joint(context.object)

        column = layout.column(align=True)
        column.label(text="Type: %s" % (joint.type or "unknown"))
        column.label(text="Moves: %s" % (joint.body_a_name or "?"))
        column.label(text="Anchored to: %s" % (joint.body_b_name or "?"))

        if joint.wrapper:
            column.label(text="Wrapped in: %s" % joint.wrapper)

        if joint.type == "Ragdoll":
            self._angles(layout, (
                ("Cone", joint.cone_max, None),
                ("Plane", *joint.plane_range),
                ("Twist", *joint.twist_range),
            ))
        elif joint.type == "LimitedHinge":
            self._angles(layout, (("Hinge", *joint.hinge_range),))

        far = joint.far_frame
        layout.label(text="Far frame: %s" % ("present" if far is not None else "not stated"),
                     icon="CHECKMARK" if far is not None else "ERROR")

    @staticmethod
    def _angles(layout, rows):
        import math
        box = layout.box()
        box.label(text="Limits (degrees)")
        for name, low, high in rows:
            if low is None and high is None:
                continue
            if high is None:
                box.label(text="%s: %.1f" % (name, math.degrees(low)))
            else:
                box.label(text="%s: %.1f to %.1f" % (name, math.degrees(low), math.degrees(high)))


def _signature(obj):
    from . import limits
    return limits.signature(obj)


CLASSES = (SKHK_PT_panel, SKHK_PT_joint)
