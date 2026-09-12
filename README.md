# Skyrim Havok Constraints

Per-host scripts that turn the Havok ragdoll in a NIFBX or HKFBX export into
constraints the DCC can actually use, and write them back when you are done.

| | | Verified |
| --- | --- | --- |
| [`blender/`](blender) | add-on, `RigidBodyConstraint` + `LIMIT_ROTATION` | in Blender 5.0.1 |
| [`maya/`](maya) | `maya.cmds`, Bullet six-DOF + `transformLimits` | fixture only |
| [`max/`](max) | `pymxs`, MassFX `UConstraint` + rotation limits | fixture only |

Only the Blender add-on has been run in its host. Maya and Max are tested against
a fixture taken off a real ragdoll with a recording stand-in for the host API,
which catches a wrong property name, enum, unit or axis and cannot catch the
host's own semantics. Each README says what to check first.

## Why it exists

FBX cannot carry a ragdoll. Its own constraint objects — `FbxConstraintParent`,
`FbxConstraintAim` and the rest — are *animation* constraints: no angular
limits, no friction, no second frame, no rigid body. Blender's FBX importer
discards them in any case, 3ds Max does not read them, and Maya reads six types
none of which is a joint limit. ck-cmd wrote that route and commented it out.

So [NIFBX](https://github.com/aerisarn-two/NIFBX) and HKFBX carry the ragdoll as
properties on empty objects instead, and the translation happens at each end.
These are those ends. The reasoning, the measurements and the rules they
implement are in `docs/dcc-constraint-interop-spec.md` in NIFBX.

The payoff is that inside the DCC the link between two bodies is a **reference** —
a Blender pointer, a Maya connection, a Max node reference — not a name. Rename
every body in the scene and nothing breaks; on the way out the names are
regenerated from the references. That retires the 63-character truncation that
costs 19% of vanilla joint names their second half.

## What they do

Two paths in each host, because two people want this and they want different
things.

**Ragdoll (physics)** — `Properties ▸ Physics ▸ Build Rigid Body Constraints`.
Gives every collision shape a Blender rigid body with its Havok mass, friction,
restitution and damping, and every attachment point a `GENERIC` rigid body
constraint carrying the cone, plane and twist ranges.

Bodies are created **passive and kinematic**. A Skyrim body is parented to a
bone, and Blender's parenting overrides the simulation, so an active body would
be created and then not move — which looks like a bug here rather than the two
systems disagreeing. Turning the ragdoll on starts with unparenting, and that is
your decision to make.

**Posing (no physics)** — `Build Bone Limits`. Puts the same angular ranges on
the pose bones as `LIMIT_ROTATION` constraints, clamping the pose live with no
simulation at all. This is what an animator wants; the rigid bodies are what a
TD tuning a ragdoll wants.

**Before export** — `Bake Constraints to Properties`. Writes edited constraints
back into the properties the exporters read.

Both build paths are reversible and neither touches a property.

## Two things worth knowing

**A constraint nobody touched bakes to nothing.** The mapping is lossy in one
place — a Havok cone is one half-angle capping deviation in every direction at
once, and Blender has no cone, so it becomes a symmetric limit on one axis.
Regenerating properties on every bake would therefore degrade the file a little
each time even if you only opened it and looked. A fingerprint stored at build
time is compared against the live state, and only genuinely edited joints are
rewritten.

**Every property this add-on does not understand is left exactly alone.** A
stiff spring's stiffness, a chain's links, a wrapper's breaking threshold: the
`hkc_` dump is what makes a NIF round trip byte-exact, and it is not this
add-on's to rewrite.

## Installing (Blender)

Blender 4.2 or newer. `Edit ▸ Preferences ▸ Add-ons ▸ Install from Disk`, and
pick the `skyrim_havok_constraints` folder zipped, or drop the folder into your
`scripts/addons` directory.

## Testing

```
tests/run.sh path/to/skeleton_cow.fbx
```

28 checks against a real creature ragdoll — 23 joints, 24 bodies — covering the
build, both reversals, and rules R1 to R4 of the spec. There is no bundled
fixture on purpose: any skeleton NIFBX or HKFBX converted will do, and the suite
is only worth anything if it runs against files nobody wrote for a test.

Two Blender facts the suite exists to pin down, both found by running it:

- `bpy.context.temp_override` **segfaults Blender 5.0.1 in background mode**
  when a rigid body operator runs inside it. Setting `view_layer.objects.active`
  does not.
- **A hidden object has no evaluated transform.** `matrix_world` comes back with
  an identity scale instead of the armature's, silently. Six of the cow's
  twenty-four bodies arrive hidden, and deriving a joint frame from one of them
  lands a whole unit out of place.

Do not pass `--factory-startup`: it leaves `io_scene_fbx`'s operator properties
unregistered and the exporter dies on its own `use_space_transform`.
