"""The operator: one button, because there is only one thing to do."""

import bpy

from . import fix


class SKS_OT_fix_scale(bpy.types.Operator):
    """Rescale objects Blender imported hidden, which it leaves at the wrong scale"""

    bl_idname = "sks.fix_import_scale"
    bl_label = "Fix Hidden Object Scale"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        corrected, unparented = fix.fix(context.scene)

        for name in unparented:
            self.report(
                {"WARNING"},
                f"{name} is hidden and has no parent, so there is nothing to take its scale from",
            )

        if not corrected:
            self.report({"INFO"}, "every object already agrees with its parent")
            return {"CANCELLED"}

        self.report({"INFO"}, f"{len(corrected)} object(s) rescaled")

        for name in corrected:
            print(f"[skyrim import scale] rescaled {name}")

        return {"FINISHED"}


CLASSES = (SKS_OT_fix_scale,)
