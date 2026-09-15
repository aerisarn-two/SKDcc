"""The two buttons."""

import bpy

from . import build


class SKDCC_OT_mark_sockets(bpy.types.Operator):
    bl_idname = "skdcc.mark_sockets"
    bl_label = "Mark Sockets"
    bl_description = ("Turn off Deform on every bone that weights nothing, gather them "
                      "in a Sockets collection, and cut back the tails Blender invented")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        report = build.build(context.scene)
        self.report({"INFO"}, str(report))

        for line in report.notes:
            self.report({"WARNING"}, line)

        return {"FINISHED"}


class SKDCC_OT_clear_sockets(bpy.types.Operator):
    bl_idname = "skdcc.clear_sockets"
    bl_label = "Clear Socket Marks"
    bl_description = "Put every marked bone back to deforming and remove the collection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        restored = build.clear(context.scene)
        self.report({"INFO"}, f"{restored} bone(s) put back")

        return {"FINISHED"}


_classes = (SKDCC_OT_mark_sockets, SKDCC_OT_clear_sockets)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
