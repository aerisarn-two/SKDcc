"""The operators: build the particle systems, and take them away again."""

import bpy

from . import build, schema


class SKP_OT_build(bpy.types.Operator):
    """Build Blender particle systems from the NIF properties in this scene"""

    bl_idname = "skp.build_particles"
    bl_label = "Build Particle Systems"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        report = build.build(context.scene)

        if not report.systems and not report.skipped:
            self.report({"WARNING"}, "no particle systems in this scene")
            return {"CANCELLED"}

        for line in report.skipped:
            self.report({"WARNING"}, line)

        # Notes go to the console rather than the status bar: they are the
        # things a person needs when the effect looks wrong later, not now.
        for line in report.notes:
            print(f"[skyrim particles] {line}")

        self.report({"INFO"}, str(report))

        return {"FINISHED"}


class SKP_OT_clear(bpy.types.Operator):
    """Remove the particle systems this add-on built"""

    bl_idname = "skp.clear_particles"
    bl_label = "Clear Particle Systems"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = build.clear(context.scene)

        self.report({"INFO"}, f"{removed} particle system(s) removed")

        return {"FINISHED"}


CLASSES = (SKP_OT_build, SKP_OT_clear)
