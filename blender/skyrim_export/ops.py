"""The button."""

import bpy
from bpy_extras.io_utils import ExportHelper

from . import export


class SKDCC_OT_export_fbx(bpy.types.Operator, ExportHelper):
    bl_idname = "skdcc.export_fbx"
    bl_label = "Export FBX for Skyrim"
    bl_description = ("Write the scene as the NIF and Havok converters expect it: "
                      "no axis conversion, rigs at rest, custom properties kept")
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(default="*.fbx", options={"HIDDEN"})

    animations: bpy.props.BoolProperty(
        name="Animations",
        description=("Write every action as an animation stack. A creature's Havok "
                     "clips are found again on the way back, so leave this on unless "
                     "the animation is not wanted -- it is most of the file"),
        default=True)

    def execute(self, context):
        report = export.write(context.scene, self.filepath, self.animations)
        self.report({"INFO"}, str(report))

        return {"FINISHED"}


def menu(self, context):
    self.layout.operator(SKDCC_OT_export_fbx.bl_idname, text="Skyrim (.fbx)")


def register():
    bpy.utils.register_class(SKDCC_OT_export_fbx)
    bpy.types.TOPBAR_MT_file_export.append(menu)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu)
    bpy.utils.unregister_class(SKDCC_OT_export_fbx)
