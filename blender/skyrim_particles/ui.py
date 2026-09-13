"""Where the buttons live: beside the particles, on the node that carries one."""

import bpy

from . import build, schema


class SKP_PT_panel(bpy.types.Panel):
    bl_label = "Skyrim Particles"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "particle"

    def draw(self, context):
        layout = self.layout

        layout.operator("skp.build_particles", icon="PARTICLES")
        layout.operator("skp.clear_particles", icon="X")

        obj = context.object

        if obj is None:
            return

        if build.is_system(obj):
            box = layout.box()
            box.label(text=f"{obj.get(schema.SYSTEM, '')}", icon="INFO")

            emitter = build.emitter_of(obj)

            if emitter is not None:
                box.label(text=emitter.get(schema.MODIFIER, ""))

            box.label(text=f"{len(build.modifiers_of(obj))} modifier(s)")


CLASSES = (SKP_PT_panel,)
