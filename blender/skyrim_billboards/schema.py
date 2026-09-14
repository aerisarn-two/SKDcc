"""What NIFBX writes for a node that turns to face the viewer.

Mirror of ``FbxNodeType``. A ``NiBillboardNode`` is aimed at the camera by the
engine every frame, so a converted scene shows it as a fixed plane -- correct
from one direction and wrong from every other.
"""

#: The block type, on the node. A billboard is whichever node says this.
BLOCK_TYPE = "nif_block_type"
BILLBOARD = "NiBillboardNode"

#: Prefix on the class's own fields.
FIELD_PREFIX = "nif_own_"

#: How it faces, from ``BillboardMode`` in nif.xml:
#:
#:     0  ALWAYS_FACE_CAMERA      3  ALWAYS_FACE_CENTER
#:     1  ROTATE_ABOUT_UP         4  RIGID_FACE_CENTER
#:     2  RIGID_FACE_CAMERA       5  BSROTATE_ABOUT_UP
#:                                9  ROTATE_ABOUT_UP2
MODE = FIELD_PREFIX + "Billboard Mode"

#: The modes that turn about the up axis only, keeping the node upright. The
#: rest face the viewer outright. The campfire has one of each: its heat haze
#: is mode 1 and the glow over the fire is mode 3.
ABOUT_UP = (1, 5, 9)

#: What this add-on calls the constraints it adds.
#:
#: A name rather than a custom property, because a constraint is one of the few
#: things in Blender that will not carry one -- ``bpy_struct[key] = val: id
#: properties not supported for this type``. Nothing is exported from a
#: constraint either, so there is nothing here for NIFBX to skip: what a
#: constraint changes is the evaluated transform, and that is handled on the
#: other side by carrying the billboard's authored rotation and preferring it
#: (``FbxNodeType.BillboardRotationProperty``).
CONSTRAINT_NAME = "skb_billboard"
