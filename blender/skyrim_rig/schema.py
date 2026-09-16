"""What this add-on writes, and what it reads back."""

#: On a bone: that this pass decided it deforms nothing. Written so the pass can
#: be undone exactly, and so a second run does not have to work it out again.
SOCKET = "skdcc_socket"

#: On the armature: that the pass has run, and the cap it used.
MARKED = "skdcc_sockets_marked"
CAP = "skdcc_socket_length"

#: Where the non-deforming bones are collected, for hiding in one go.
COLLECTION = "Sockets"

#: The marker drawn in place of a bone whose direction is invented. Held in
#: `bpy.data` and deliberately never linked to a scene, so it is a shape and
#: not an object the exporter can find.
MARKER = "SKDcc Joint"
