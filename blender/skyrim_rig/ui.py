"""Where the buttons live."""

import bpy

from . import schema


class SKDCC_PT_rig(bpy.types.Panel):
    bl_label = "Skyrim Rig"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "ARMATURE"

    def draw(self, context):
        layout = self.layout
        armature = context.object

        if schema.MARKED in armature.keys():
            marked = sum(1 for b in armature.data.bones if schema.SOCKET in b.keys())
            layout.label(text=f"{marked} socket(s) marked", icon="CHECKMARK")
            layout.operator("skdcc.clear_sockets", icon="X")
        else:
            layout.label(text="Not marked yet")
            layout.operator("skdcc.mark_sockets", icon="BONE_DATA")


def register():
    bpy.utils.register_class(SKDCC_PT_rig)


def unregister():
    bpy.utils.unregister_class(SKDCC_PT_rig)
