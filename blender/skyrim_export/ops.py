"""The button."""

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import export, load


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


class SKDCC_OT_import_fbx(bpy.types.Operator, ImportHelper):
    bl_idname = "skdcc.import_fbx"
    bl_label = "Import FBX from Skyrim"
    bl_description = ("Read a Skyrim FBX with its bones aimed down their chains, "
                      "keeping the rest pose the file states so it can go back")
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".fbx"
    filter_glob: bpy.props.StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        bones, armatures = load.read(self.filepath)
        self.report({"INFO"}, "%d bones in %d armatures" % (bones, armatures))

        return {"FINISHED"}


def export_menu(self, context):
    self.layout.operator(SKDCC_OT_export_fbx.bl_idname, text="Skyrim (.fbx)")


def import_menu(self, context):
    self.layout.operator(SKDCC_OT_import_fbx.bl_idname, text="Skyrim (.fbx)")


def register():
    bpy.utils.register_class(SKDCC_OT_export_fbx)
    bpy.utils.register_class(SKDCC_OT_import_fbx)
    bpy.types.TOPBAR_MT_file_export.append(export_menu)
    bpy.types.TOPBAR_MT_file_import.append(import_menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(import_menu)
    bpy.types.TOPBAR_MT_file_export.remove(export_menu)
    bpy.utils.unregister_class(SKDCC_OT_import_fbx)
    bpy.utils.unregister_class(SKDCC_OT_export_fbx)
