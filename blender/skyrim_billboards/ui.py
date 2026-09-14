"""Where the buttons live: on the object, beside its constraints."""

import bpy

from . import build, schema


class SKB_PT_panel(bpy.types.Panel):
    bl_label = "Skyrim Billboard"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "constraint"

    def draw(self, context):
        layout = self.layout

        layout.operator("skb.build_billboards", icon="CON_TRACKTO")
        layout.operator("skb.clear_billboards", icon="X")

        obj = context.object

        if obj is None or not build.is_billboard(obj):
            return

        box = layout.box()
        box.label(text=f"mode {obj.get(schema.MODE, '?')}", icon="INFO")
        box.label(
            text="turns about up" if build._mode(obj) in schema.ABOUT_UP else "faces the viewer"
        )


CLASSES = (SKB_PT_panel,)
