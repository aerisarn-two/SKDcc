"""The operators: build the materials, and put them back."""

import bpy

from . import build


class SKM_OT_build(bpy.types.Operator):
    """Rebuild Blender materials from the NIF shader properties in this scene"""

    bl_idname = "skm.build_materials"
    bl_label = "Build Skyrim Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        report = build.build(context.scene)

        if not report.materials and not report.skipped:
            self.report({"WARNING"}, "no Skyrim shader properties in this scene")
            return {"CANCELLED"}

        for line in report.skipped:
            self.report({"WARNING"}, line)

        # Notes go to the console: they are what a person needs when the
        # material looks wrong later, not while they are pressing the button.
        for line in report.notes:
            print(f"[skyrim materials] {line}")

        self.report({"INFO"}, str(report))

        return {"FINISHED"}


class SKM_OT_clear(bpy.types.Operator):
    """Put the materials this add-on built back to a plain Principled BSDF"""

    bl_idname = "skm.clear_materials"
    bl_label = "Clear Skyrim Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cleared = build.clear(context.scene)

        self.report({"INFO"}, f"{cleared} material(s) reset")

        return {"FINISHED"}


CLASSES = (SKM_OT_build, SKM_OT_clear)
