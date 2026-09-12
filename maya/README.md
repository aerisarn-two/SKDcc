# Maya

```python
import sys
sys.path.append("/path/to/SKDcc/maya")

import skhk_maya
skhk_maya.install()              # adds a "Skyrim Havok" menu
skhk_maya.build_constraints()    # or call it directly
```

Import the FBX with **Include ▸ Extra Attributes** on, or the properties this
reads will not be in the scene. Maya carries custom properties on transform
nodes only — `FbxGeometry` has no user properties — which is fine here, because
everything is on a transform by construction.

## The two paths

**Build Rigid Body Constraints** needs the Bullet plug-in, which installs with
Maya and has shipped in every version through 2026. It is loaded on demand if it
is merely not autoloaded. Bodies are made **static**, for the reason the Blender
add-on makes them passive: a Skyrim body hangs off a joint, parenting beats the
simulation, and a dynamic body would be created and then not move.

**Build Joint Limits** needs no plug-in at all — it is `transformLimits` on the
joint each body rides — and is the path an animator wants: the limits clamp the
pose as the rig is handled, with nothing simulating.

**Bake Constraints to Properties** writes edits back, ready to export.

## Six degrees of freedom, not cone-twist

Cone-twist is Bullet's ragdoll joint and it is the wrong target. Maya's Bullet
node exposes `angularConstraintMaxX/Y/Z` for a cone-twist but
`angularConstraintMinX/Y/Z` **only** for the six-DOF types, because a cone-twist
span is a symmetric half-angle. Havok's plane and twist limits are not symmetric.

The cow's stifle runs **−45° to +9°**. A symmetric span cannot hold that; faking
it means centring the frame on the midpoint and halving the range, which changes
the frame and then has to be undone on export. Six-DOF takes both bounds
directly and leaves the frame alone — and the frame is already right, because the
attachment point's own local X, Y and Z are the Havok frame's axes.

## What has and has not been verified

The mapping, the attribute names, the enum values, the unit handling, the axis
assignment, the rename recovery and rules R1–R4 are all covered by
`tests/test_maya.py`, which runs against a fixture taken off a vanilla creature
skeleton with a recording stand-in for `maya.cmds`. It catches a wrong attribute
name, a wrong enum, a wrong unit or a wrong axis.

**It has never been run in Maya.** Whether Bullet is content with a six-DOF
constraint built this way, and whether `CreateRigidBody` behaves as its 2016
source suggests, are questions only Maya answers, and they have not been asked.
Treat the Bullet path as unproven and the `transformLimits` path as low risk.

Two things to check first in a real Maya, both of which the tests can only assume:

- the unit of `angularConstraintMin/Max` — `mayaenv.to_ui_angle` asks the
  attribute whether it is a `doubleAngle` and converts accordingly, which is
  right if Bullet declares them as angles and right if it declares them as plain
  degrees, but not if it declares them as plain *radians*;
- that `RigidBody.CreateRigidBody.command(transformName=..., bAttachSelected=False)`
  still takes those arguments. Maya's shipped module is the authority; this was
  written against the 2016 sources, which are the newest published ones.
