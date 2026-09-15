"""Writing an edited constraint back into the properties.

The rules this implements are R1-R5 of ``dcc-constraint-interop-spec.md``, and
the one that matters most is R2: **a constraint nobody touched is written back
untouched.** The mapping in :mod:`limits` is lossy in one place -- a Havok cone
is not a per-axis limit -- so regenerating properties on every bake would
degrade the file a little each time even when the scene was only opened and
looked at. Comparing a stored fingerprint against the current state is what
makes a no-op round trip actually a no-op.
"""

import mathutils

from . import bodies, limits, schema
from .blender_compat import evaluated
from .joint import Joint, joints_in

#: What Blender will hold in an object name. Past this it stores a truncated
#: name with a hash on the end, so a longer name cannot be written at all -- it
#: can only be replaced by something else.
#:
#: Here rather than in `schema`, which is the three hosts' shared vocabulary for
#: what the *file* calls things. This is Blender's own limit; Maya and Max do
#: not share it.
NAME_LIMIT = 63


class Baked:
    def __init__(self):
        self.rewritten = 0
        self.unchanged = 0
        self.renamed = 0
        self.problems = []

    def __str__(self):
        text = "%d rewritten, %d unchanged" % (self.rewritten, self.unchanged)
        if self.renamed:
            text += ", %d renamed" % self.renamed
        if self.problems:
            text += ", %d problem%s" % (len(self.problems),
                                        "" if len(self.problems) == 1 else "s")
        return text


def bake(objects):
    """Write every edited constraint back to its properties."""
    result = Baked()
    pool = list(objects)

    with evaluated(pool):
        _bake(pool, result)

    return result


def _bake(pool, result):
    for obj in joints_in(pool):
        rbc = obj.rigid_body_constraint

        if rbc is None:
            continue

        joint = Joint(obj)

        if obj.get(schema.SIGNATURE, None) == limits.signature(obj):
            result.unchanged += 1
            continue

        _write_names(obj, joint, rbc, result)
        _write_limits(obj, joint, rbc)
        _write_far_frame(obj, joint, pool, result)

        obj[schema.SIGNATURE] = limits.signature(obj)
        result.rewritten += 1


# --- R3: names come from the references, never the other way round ---------


def _write_names(obj, joint, rbc, result):
    """Rebuild the body names and the node name from the object references.

    This is the point of the whole design: inside Blender the link is a pointer
    that survives any rename, and the names in the file are regenerated from it
    on the way out. A joint whose name Blender truncated comes back whole.
    """
    owner_a = _owner_of(rbc.object1)
    owner_b = _owner_of(rbc.object2)

    if owner_a is None or owner_b is None:
        result.problems.append("%s: a constraint object is not a Havok body" % obj.name)
        return

    obj[schema.BODY_A] = _havok_name_of(owner_a)
    obj[schema.BODY_B] = _havok_name_of(owner_b)

    body_a = _clean_name(owner_a)
    body_b = _clean_name(owner_b)

    wanted = "%s%s%s%s" % (body_b, schema.NAME_SEPARATOR, body_a, schema.ATTACH_SUFFIX)

    # The properties above are the answer; the name is a courtesy to whatever
    # reads names. It is only worth writing if Blender can hold it.
    #
    # An object name caps at 63 bytes and the tail is replaced with a hash past
    # that. A draugr's forearm-to-hand joint wants 85 -- so assigning it stores
    # something like `..._rb_con_NPC4f2a91c6`, which is not the name asked for
    # and is worse than the one already there. Writing the far frame's name then
    # pushes it further over.
    if len(wanted.encode("utf-8")) > NAME_LIMIT:
        # Keep the separator, though: that is how ck-cmd recognises one of these
        # at all, and a name with no `_con_` in it is invisible to it.
        if schema.NAME_SEPARATOR not in obj.name:
            obj.name = _short_name(body_a, body_b)
            result.renamed += 1

        result.problems.append(
            "%s: the full name is %d bytes and Blender holds %d, so the bodies "
            "are carried as properties only"
            % (obj.name, len(wanted.encode("utf-8")), NAME_LIMIT))
        return

    if obj.name != wanted:
        far = joint.far_frame
        obj.name = wanted
        if far is not None:
            far.name = wanted + schema.FAR_FRAME_SUFFIX
        result.renamed += 1


def _short_name(body_a, body_b):
    """A name that fits and still says what kind of node this is.

    Not a reference -- the properties hold that. Just enough for a reader that
    goes by name to see an attachment point, with whatever of the body names
    will fit either side of the separator.
    """
    room = NAME_LIMIT - len(schema.NAME_SEPARATOR) - len(schema.ATTACH_SUFFIX)
    half = max(room // 2, 1)

    return "%s%s%s%s" % (
        body_b[:half], schema.NAME_SEPARATOR, body_a[:half], schema.ATTACH_SUFFIX)


def _owner_of(shape):
    """The Havok body a rigid body shape belongs to.

    The rigid body lives on the shape mesh and the Havok body is its parent, so
    the object wanted is the parent's -- unless the body carries the shape
    itself, which a single-shape body does.
    """
    if shape is None:
        return None

    owner = shape if _clean_name(shape).endswith(schema.BODY_SUFFIX) else shape.parent

    if owner is None:
        return None

    return owner if _clean_name(owner).endswith(
        (schema.BODY_SUFFIX, schema.PHANTOM_SUFFIX)) else None


def _clean_name(obj):
    """An object's name with Blender's ``.001`` off, which is a Blender fact
    and not part of the file."""
    head, _, tail = obj.name.rpartition(".")

    return head if head and tail.isdigit() else obj.name


def _havok_name_of(owner):
    """The name a constraint calls this body by.

    Two vocabularies meet here. A creature exported with its skeleton.hkx has
    been through SKAssets' joint bridge, which rewrites ``constraint_body_a``
    and ``constraint_body_b`` into the *ragdoll's* names because that is what
    HKFBX reads them as, while the node names stay in the mesh's. The body
    itself carries the translation, under ``hkb_ragdoll_bone``.

    So the reference answers in whichever vocabulary the scene is written in:
    the ragdoll's when the bodies know one, the mesh's when they do not. Taking
    the object name unconditionally would quietly move a bridged joint back
    into mesh names, and HKFBX would then find neither body.
    """
    return str(owner.get(schema.RAGDOLL_BONE, "")) or _clean_name(owner)


# --- R1: the descriptor dump is updated, never replaced --------------------


def _write_limits(obj, joint, rbc):
    """Put the edited angles back, under both spellings.

    Both, because both are read: the ``hkc_`` field is what NIFBX rebuilds the
    NIF from, and the shared name is what ck-cmd and HKFBX read. Writing one
    and not the other leaves the file disagreeing with itself.

    Every other property is left exactly as it was -- R1. A stiff spring's
    stiffness, a chain's links, a wrapper's breaking threshold: this add-on has
    no opinion about any of them and must not have one.
    """
    if rbc.type == "POINT":
        return

    angular = {
        axis: (getattr(rbc, "limit_ang_%s_lower" % axis),
               getattr(rbc, "limit_ang_%s_upper" % axis))
        if getattr(rbc, "use_limit_ang_%s" % axis) else None
        for axis in "xyz"
    }

    if joint.type == "Ragdoll":
        _pair(obj, angular["x"], schema.TWIST_MIN, schema.TWIST_MAX,
              "Twist Min Angle", "Twist Max Angle")
        _pair(obj, angular["y"], schema.PLANE_MIN, schema.PLANE_MAX,
              "Plane Min Angle", "Plane Max Angle")

        # The cone came out as a symmetric pair and goes back as the half
        # angle it was. Taking the larger magnitude rather than the upper
        # bound alone keeps a cone the user widened by dragging the lower
        # limit instead of the upper.
        if angular["z"] is not None:
            lower, upper = angular["z"]
            _scalar(obj, max(abs(lower), abs(upper)), schema.CONE_MAX, "Cone Max Angle")

    elif joint.type == "LimitedHinge":
        _pair(obj, angular["x"], schema.MIN_ANGLE, schema.MAX_ANGLE,
              "Min Angle", "Max Angle")


def _pair(obj, limit, min_property, max_property, min_field, max_field):
    if limit is None:
        return
    lower, upper = limit
    _scalar(obj, min(lower, upper), min_property, min_field)
    _scalar(obj, max(lower, upper), max_property, max_field)


def _scalar(obj, value, shared_property, field_name):
    """One angle, under both names, each in the type its reader expects.

    The shared property is a float because that is what NIFBX writes and what
    Maya and Max hand to a script as a number. The ``hkc_`` field is a string
    because the descriptor dump is strings throughout -- it has to carry
    vectors and flags in the same store -- and a reader that meets a double
    there will not parse it.
    """
    obj[shared_property] = float(value)

    key = schema.field(field_name)
    if key in obj.keys():
        obj[key] = repr(float(value))


# --- R4: both frames survive ----------------------------------------------


def _write_far_frame(obj, joint, pool, result):
    """Recompute frame A from where the joint now is.

    Havok stores the joint twice, once in each body's space; Blender stores it
    once, as the constraint object's transform. So the far frame is derived
    rather than carried: it is the joint's placement seen from body A. This is
    the derivation ck-cmd gets wrong -- spec §3.2, where it copies the pivot's
    X into all three components -- and both matrices are to hand here.

The scale check is a backstop rather than an expected path. ``bake`` forces
    every object it touches to be evaluated first, because a hidden one reports
    an identity scale instead of the armature's and the derivation then lands a
    whole unit out -- see :func:`blender_compat.evaluated`. If two bodies still
    disagree about scale after that, something is going on that this cannot
    model, and the frame is left alone and said to be left alone: a frame A that
    is quietly wrong breaks the ragdoll, where one that is quietly old is only
    what every ck-cmd export already ships.
    """
    far = joint.far_frame

    if far is None:
        return

    body_a = bodies.find_body(pool, joint.body_a_name)

    if body_a is None:
        return

    scale_a = body_a.matrix_world.to_scale()
    scale_joint = obj.matrix_world.to_scale()

    if max(abs(a - b) for a, b in zip(scale_a, scale_joint)) > 1e-4:
        result.problems.append(
            "%s: frame A not updated -- %s and the joint have different world "
            "scales (%.3g against %.3g), usually Blender's leaf bone handling"
            % (obj.name, body_a.name, scale_a[0], scale_joint[0]))
        return

    relative = body_a.matrix_world.inverted_safe() @ obj.matrix_world

    # A joint frame is a rotation and a pivot; any scale in the product is an
    # artefact of the two chains, so it is dropped rather than written out.
    location, rotation, _ = relative.decompose()

    # Stored as a quaternion, not as Euler angles. An object keeps its rotation
    # the way its `rotation_mode` says, and assigning a matrix decomposes into
    # that -- so a frame landing near Euler's gimbal lock is quantised badly on
    # the way in. The chicken's pelvis-to-neck frame is one: through XYZ it
    # comes back 2.7e-5 out, through the quaternion 3e-7, from the same matrix.
    # Nothing downstream reads the mode; the exporter writes what it composes.
    far.rotation_mode = "QUATERNION"
    far.matrix_basis = (mathutils.Matrix.Translation(location)
                        @ rotation.to_matrix().to_4x4())
