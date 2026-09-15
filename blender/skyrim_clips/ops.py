"""The chooser."""

import bpy

from . import play


class SKDCC_OT_play_clip(bpy.types.Operator):
    bl_idname = "skdcc.play_clip"
    bl_label = "Play Clip"
    bl_description = "Put the chosen clip on the rig and set the scene to its length"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        clip, problem = play.play(context.scene, context.scene.skdcc_clip)

        if problem is not None:
            self.report({"WARNING"}, problem)
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"{clip.name}: frames {context.scene.frame_start}-{context.scene.frame_end}")

        return {"FINISHED"}


class SKDCC_OT_clear_clip(bpy.types.Operator):
    bl_idname = "skdcc.clear_clip"
    bl_label = "Take It Off"
    bl_description = ("Unassign the clip, so the NLA tracks drive the rig. An assigned "
                      "clip is evaluated after the tracks and hides them")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not play.clear(context.scene):
            self.report({"WARNING"}, "there is no armature with bones in this scene")
            return {"CANCELLED"}

        self.report({"INFO"}, "no clip assigned; the NLA tracks drive the rig now")

        return {"FINISHED"}


class SKDCC_PT_clips(bpy.types.Panel):
    bl_label = "Skyrim Clips"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Skyrim"

    def draw(self, context):
        layout = self.layout
        rig = play.rig_of(context.scene)

        if rig is None:
            layout.label(text="no armature with bones", icon="INFO")
            return

        layout.label(text=rig.name, icon="ARMATURE_DATA")

        current = rig.animation_data.action if rig.animation_data else None
        layout.label(text=f"playing: {current.name if current else 'nothing'}")

        layout.prop_search(
            context.scene, "skdcc_clip", bpy.data, "actions", text="", icon="ACTION")

        layout.operator(SKDCC_OT_play_clip.bl_idname, icon="PLAY")
        layout.operator(SKDCC_OT_clear_clip.bl_idname, icon="X")
        layout.label(text=f"{len(bpy.data.actions)} clips in this file")


_classes = (SKDCC_OT_play_clip, SKDCC_OT_clear_clip, SKDCC_PT_clips)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.skdcc_clip = bpy.props.StringProperty(
        name="Clip",
        description="Which of the creature's animations to put on the rig")


def unregister():
    del bpy.types.Scene.skdcc_clip

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
