# 3ds Max

```python
import sys
sys.path.append(r"C:\path\to\SKDcc\max")

import skhk_max
skhk_max.report(skhk_max.build_constraints())
```

Python through `pymxs`, not MAXScript, so the same architecture and the same kind
of test serve all three hosts. Max has shipped Python since 2015.

Import the FBX with custom properties on. Max has **two** places a foreign FBX
property can land — a typed custom attribute, or a line in the node's
User-Defined Properties buffer — and the importer's choice is not documented
either way, so `maxenv.read_raw` tries the custom attribute, then `getUserProp`,
then parses the raw buffer itself. Nothing above that layer needs to know which
arrived.

## The two paths

**Build Constraints** needs MassFX. Bodies get a `MassFX_RBody` modifier and are
made **Static**, for the reason the other hosts use passive bodies: a Skyrim body
is parented into the rig, Max's parenting beats the simulation, and a dynamic body
would be created and then not move.

**Build Rotation Limits** needs no plug-in — it is the rotation controller's own
limits on the bone each body rides — and is the path an animator wants.

**Bake** writes edits back, ready to export.

## Max is the one host that needs the frame trick

A MassFX `UConstraint` is a PhysX D6, and its three rotational limits do not agree
about symmetry:

| Axis | Max | Havok | Result |
| --- | --- | --- | --- |
| X | `twistAngleLow` / `twistAngleHigh` — a pair | twist or hinge range, asymmetric | **exact** |
| Y | `swing1Angle` — one half-angle | plane range, asymmetric | **may need centring** |
| Z | `swing2Angle` — one half-angle | cone, already a half-angle | **exact** |

"If you set Angle Limit to 45 degrees, the total allowed rotation equals 90" — the
swings are symmetric about the frame; the twist pair is not. So the cow's stifle at
−45° to +9° goes across exactly, on the twist axis, and only a lopsided *plane*
limit needs spec §5.3's treatment:

```
offset = (max + min) / 2      turn the constraint frame by this, about local Y
span   = (max - min) / 2      the symmetric limit
```

Four of the cow's eleven ragdoll joints need it. The offset is written to the joint
as `skhk_swing_offset`, which is what makes it **invertible**: the bake reads the
recorded offset rather than guessing, so a round trip returns the original range
bit for bit instead of recentring the joint a little each time.

A range lying entirely to one side of zero cannot be spelled at all, because Max's
limits are magnitudes about the frame. None of the 34 ranges in the cow skeleton is
like that; a hand-authored one could be, and it is reported rather than flattened.

## What has and has not been verified

`tests/test_max.py` runs against a fixture taken off a vanilla creature skeleton
with a recording stand-in for `pymxs`: 31 checks covering the property names, the
mode enums, degrees, the axis assignment, the centre/uncentre round trip, and rules
R1–R4. It catches a wrong property name, a wrong enum, a wrong unit or a wrong
axis.

**It has never been run in 3ds Max**, and Max does not run on this machine at all.
Treat the MassFX path as unproven.

Three things to check first in a real Max, none of which a fixture can settle:

- **`MassFX_RBody.type`.** The modifier's default is 1 and the panel's default body
  is Dynamic, so the numbering here reads 1 Dynamic, 2 Kinematic, 3 Static from the
  panel's order. If Static is not 3, every body comes in with the wrong kind.
- **The sign convention of `twistAngleLow`/`twistAngleHigh`.** The reference calls
  them "absolute degrees for each edge of the limit" and both default to 45, so
  they are written here as magnitudes — Low the negative edge, High the positive.
  If Max means them signed, every twist range comes out mirrored.
- **Whether the FBX importer files properties as custom attributes or as UDP.** Both
  are read, so this should not matter, but it decides whether `write_raw` puts an
  edit back as a typed value or as buffer text.
