# Skyrim Havok Constraints

Per-host scripts that turn the Havok ragdoll in a NIFBX or HKFBX export into
constraints the DCC can actually use, and write them back when you are done.

| | | Verified |
| --- | --- | --- |
| [`blender/skyrim_havok_constraints`](blender/skyrim_havok_constraints) | add-on, `RigidBodyConstraint` + `LIMIT_ROTATION` | in Blender 5.0.1 |
| [`blender/skyrim_particles`](blender/skyrim_particles) | add-on, Blender particle systems | in Blender 5.0.1, over 125 systems |
| [`blender/skyrim_import_scale`](blender/skyrim_import_scale) | add-on, one button | in Blender 5.0.1 |
| [`maya/`](maya) | `maya.cmds`, Bullet six-DOF + `transformLimits` | fixture only |
| [`max/`](max) | `pymxs`, MassFX `UConstraint` + rotation limits | fixture only |

Only the Blender add-ons have been run in their host. Maya and Max are tested against
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

## Import scale

**`Properties ▸ Object ▸ Fix Hidden Object Scale`.** Blender's FBX importer
converts the file's units into the scene's — a NIF arrives in centimetres and
Blender works in metres, so everything is scaled by 0.01 on the way in — and it
does not do that for an object it imports **hidden**. Those keep world scale 1.0
and come out a hundred times too big.

Every collision proxy is hidden, and so is every node the NIF marks invisible, so
a converted mesh routinely opens with a correctly sized model sitting inside a
proxy a hundred times its size:

```
DaedricDagger_dd_0_support   0.0100   visible
DaedricDagger_rb_convex      1.0000   hidden
EdgeBlood25_support          1.0000   hidden
```

The file is not at fault. Every one of those nodes has `Lcl Scaling = 1` under a
root of scale 1, and stripping the visibility flags alone — changing nothing else
— brings all six back to 0.01. The repair recomputes the world matrix the way
Blender itself would, from the parent the object already has, so no factor is
written down and an object that was already right does not move.

## Particles

`Properties ▸ Particles ▸ Build Particle Systems` does the same job for an
effect. A NIF particle system arrives as an empty carrying the system's fields
with one child node per modifier, because FBX has no emitter and nothing that
means what `NiPSysCylinderEmitter` means. This reads that stack and builds a
Blender particle system from it: the emitter's speed, lifespan and size, the
drag modifier's damping, the rotation modifier's spin, the spawn modifier's
children.

Direction comes from the engine rather than from a guess. `NiPSEmitter::
EmitParticles` builds it as `(0,0,1)` turned by the declination and planar
angles, so a particle leaves along the emitter frame's local **+Z** — a candle
flame with a declination of zero goes straight up. Blender's `normal_factor` is
speed along the emitting *normal*, and a volume has none, so using it made every
effect fire in all directions; the speed goes on `object_align_factor` instead,
which is the same statement the engine makes. A mesh emitter set to
`VELOCITY_USE_NORMALS` is the exception the engine makes too, and there
`normal_factor` is exactly right.

Blender emits from a mesh and Skyrim emits from a volume or from a named mesh,
so the system is put on the object a mesh emitter names, or on a wire primitive
matching the box, cylinder or sphere the emitter describes. Over 40 of the
game's effect meshes — 125 systems, all four emitter kinds — every one builds.

**Units are converted, not copied.** A NIF is in the game's own units and
Blender imports it into metres, so a speed of 210 used as it stands is 210 m/s
and the splinters leave the windmill like bullets. Every length — speed, radius,
the acceleration a gravity modifier carries — is multiplied by the world scale
the emitter's own frame already has, so the factor is never written down here
and stays right if the importer ever changes what it does. The windmill's
splinters come out at 2.1 m/s under a gravity of 9.0 m/s², which is the game's
own constant landing on Earth's.

**Import effects with Automatic Bone Orientation off.** An emitter's frame is
often a bone — NIFBX writes a node as a `LimbNode` where the NIF has it in a
skeleton, and Blender turns every LimbNode into a bone — and that option
re-orients bones. Measured on a candle: with it off every emitter bone has
`+Z = (0, 0, 1)`, and with it on every one has `(0, 0, -1)`, so the flame emits
downwards. It is the right option for a creature rig and the wrong one here.

It is one direction, and deliberately. Blender's particle system is not a
superset of Skyrim's: there is no cone half-angle, and colour and size over a
particle's life live on the material rather than on the system. Those are
**reported on the console** rather than approximated, because a flat value in
place of a curve looks like a translation and behaves like a guess. The
properties stay on the nodes either way, so nothing is lost by not reading them
— `Clear Particle Systems` puts the scene back.

One thing worth knowing: a Skyrim system with no gravity modifier gets
`effector_weights.gravity = 0`. Blender pulls every particle down by default and
Skyrim does not, so a faithful build has to turn that off — and a gravity
modifier that *is* present almost always stores a strength of zero and takes its
real value from a controller, which is in the animation and not in the scene.

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
