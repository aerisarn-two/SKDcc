"""Where the buttons live: on the material, beside what they rebuild."""

import bpy

from . import build, schema


class SKM_PT_panel(bpy.types.Panel):
    bl_label = "Skyrim Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    def draw(self, context):
        layout = self.layout

        layout.operator("skm.build_materials", icon="NODE_MATERIAL")
        layout.operator("skm.clear_materials", icon="X")

        material = getattr(context, "material", None)

        if material is None or not build.is_skyrim_material(material):
            return

        box = layout.box()

        kind = (
            schema.EFFECT_SHADER
            if build.is_effect_shader(material)
            else schema.LIGHTING_SHADER
        )

        box.label(text=kind, icon="INFO")

        if material.get(schema.SHADER_TYPE):
            box.label(text=f"type: {material[schema.SHADER_TYPE]}")

        if material.get(schema.SOURCE):
            box.label(text="rebuilt", icon="CHECKMARK")


CLASSES = (SKM_PT_panel,)
