"""The property names NIFBX and HKFBX write, and what they mean.

Mirror of ``FbxConstraintWriter`` and ``FbxSkeletonWriter``. Nothing here is
guessed: every name was read out of a real export, and the spec that defines
them is ``dcc-constraint-interop-spec.md`` in NIFBX.

Kept byte-identical to the other hosts' copies rather than shared, because a
Blender add-on has to be a self-contained folder and a Maya or Max script has to
be importable from a scripts path; none of them can reach a sibling package.
``tests/test_schema_agrees.py`` fails if the copies drift apart.

The names are already legal identifiers. NIFBX escapes a space as ``_s_``,
brackets as ``_ob_``/``_cb_`` and a colon as ``_dd_`` (``NameEncoding``), so
``NPC L Forearm [LLar]`` arrives as ``NPC_s_L_s_Forearm_s__ob_LLar_cb_`` -- and
the body properties carry the escaped spelling, so they match the node names.
"""

# --- the shared convention -------------------------------------------------

TYPE = "constraint_type"
WRAPPER = "constraint_wrapper"
FRAME = "constraint_frame"
BODY_A = "constraint_body_a"
BODY_B = "constraint_body_b"
ONE_SIDED = "constraint_one_sided"

FIELD_PREFIX = "hkc_"
NAME_SEPARATOR = "_con_"
ATTACH_SUFFIX = "_attach_point"
FAR_FRAME_SUFFIX = "_frame_a"

BODY_SUFFIX = "_rb"
PHANTOM_SUFFIX = "_sp"

# The six ck-cmd named, plus the two a limited hinge uses, as floats.
CONE_MAX = "coneMaxAngle"
PLANE_MIN = "planeMinAngle"
PLANE_MAX = "planeMaxAngle"
TWIST_MIN = "twistMinAngle"
TWIST_MAX = "twistMaxAngle"
MAX_FRICTION = "maxFriction"
MIN_ANGLE = "minAngle"
MAX_ANGLE = "maxAngle"

#: Rigid body properties, as ``FbxRigidBodyInfo`` writes them.
RB_MASS = "nif_rb_mass"
RB_FRICTION = "nif_rb_friction"
RB_RESTITUTION = "nif_rb_restitution"
RB_LINEAR_DAMPING = "nif_rb_linear_damping"
RB_ANGULAR_DAMPING = "nif_rb_angular_damping"
RB_LAYER = "nif_rb_layer"

#: Written by these scripts, never by the exporters: a fingerprint of the values
#: it put on the native constraint, so a later bake can tell an untouched
#: constraint from an edited one. See spec R2.
SIGNATURE = "skhk_signature"

#: Marks the objects this add-on created, so it can clean up after itself.
GENERATED = "skhk_generated"

#: Name given to the pose-bone constraints of the animation path.
BONE_LIMIT_NAME = "SKHK Limit"

#: Collision shape by the suffix the tessellator appends. The tokens happen to be
#: Blender's own spelling; every other host maps them to its enum, so this table
#: stays the one place the suffixes are listed.
SHAPE_SUFFIXES = (
    ("_sphere", "SPHERE"),
    ("_box", "BOX"),
    ("_capsule", "CAPSULE"),
    ("_cylinder", "CAPSULE"),
    ("_convex_list", "CONVEX_HULL"),
    ("_convex", "CONVEX_HULL"),
    ("_mopp", "MESH"),
    ("_mesh", "MESH"),
)


def collision_shape_of(name):
    """The collision shape a tessellated shape node stands for."""
    lowered = name.lower()
    for suffix, shape in SHAPE_SUFFIXES:
        if lowered.endswith(suffix) or (suffix + ".") in lowered:
            return shape
    return "CONVEX_HULL"


def field(name):
    """The property a nif.xml field is stored under: ``Cone Max Angle`` ->
    ``hkc_cone_max_angle``. The same transform ``NifFieldCodec.Key`` applies."""
    return FIELD_PREFIX + name.replace(" ", "_").lower()


#: The midpoint a swing limit was centred on, in radians, when Max's symmetric
#: Swing had to stand in for an asymmetric Havok range. Written by the Max script
#: only, and the thing that makes the approximation invertible.
SWING_OFFSET = "skhk_swing_offset"
