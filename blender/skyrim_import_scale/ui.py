"""In the Object properties, next to the transform it is repairing."""

import bpy


class SKS_PT_panel(bpy.types.Panel):
    bl_label = "Skyrim Import Scale"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    def draw(self, context):
        self.layout.operator("sks.fix_import_scale", icon="CON_SIZELIMIT")


CLASSES = (SKS_PT_panel,)
