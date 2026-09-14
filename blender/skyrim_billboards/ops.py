"""The operators: aim the billboards, and stop aiming them."""

import bpy

from . import build


class SKB_OT_build(bpy.types.Operator):
    """Aim every NiBillboardNode in this scene at the camera"""

    bl_idname = "skb.build_billboards"
    bl_label = "Aim Skyrim Billboards"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        report = build.build(context.scene)

        if not report.aimed and not report.skipped:
            self.report({"WARNING"}, "no billboard nodes in this scene")
            return {"CANCELLED"}

        for line in report.skipped:
            self.report({"WARNING"}, line)

        for line in report.notes:
            print(f"[skyrim billboards] {line}")

        self.report({"INFO"}, str(report))

        return {"FINISHED"}


class SKB_OT_clear(bpy.types.Operator):
    """Remove the aiming, leaving the rotations the file carries"""

    bl_idname = "skb.clear_billboards"
    bl_label = "Clear Skyrim Billboards"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        self.report({"INFO"}, f"{build.clear(context.scene)} constraint(s) removed")

        return {"FINISHED"}


CLASSES = (SKB_OT_build, SKB_OT_clear)
