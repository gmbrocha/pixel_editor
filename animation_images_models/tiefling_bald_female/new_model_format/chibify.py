"""
chibify.py - rest-pose proportion retarget for the PF tiefling rig.

Rebuilds the armature rest pose + skinned mesh into chibi / JRPG proportions
WITHOUT touching a single rotation keyframe. This works because every action on
this rig is quaternion rotation plus Hips translation, both of which are
proportion-independent: change the rest skeleton and the bound mesh together and
all ten actions replay correctly on the new body.

Method (rest retarget / LBS re-bind):
  1. Per bone, S_b = diag(girth, length, girth) in bone-local space.
  2. Walk the hierarchy: a child's rest offset from its parent is scaled by
     S_parent, so shortening a thigh drags the shin and foot up with it.
  3. Every vertex is moved by the weight-blended delta
         D_b = M'_b @ S_b @ M_b^-1
     i.e. linear blend skinning where the "pose" is the rest-to-chibi change.
     Skin weights, UV layout, materials and topology are all untouched.
  4. Face pass: eyes are located by sampling the base-colour texture for
     desaturated bright (sclera) vertices in the front of the head, then
     inflated in place. UVs don't move, so the painted iris scales with the
     geometry for free.
  5. Head pass: cranium bulge / jaw taper / depth flatten in head-bone space.
  6. Re-ground to z=0 and scale the Hips translation channels so the vertical
     bob and root motion match the shorter legs.

Usage:
  blender -b in.blend --python chibify.py -- out.blend [preset] ['{json overrides}']

Presets: chibi (~2.7 heads, hard chibi), jrpg (~3.4 heads, Octopath/Bravely-ish)
"""
import bpy, sys, json
from mathutils import Vector, Matrix

# ----------------------------------------------------------------------------
# TUNING - (length_scale, girth_scale) in bone space. length is along the bone.
# ----------------------------------------------------------------------------
PRESETS = {
    "chibi": {
        "bones": {
            "Hips":          (0.86, 1.10),
            "Spine02":       (0.72, 1.10),
            "Spine01":       (0.72, 1.08),
            "Spine":         (0.90, 1.06),
            "neck":          (0.28, 1.05),
            "Head":          (2.05, 2.05),
            "head_end":      (2.05, 2.05),
            "headfront":     (2.05, 2.05),
            "LeftShoulder":  (0.80, 1.10),
            "RightShoulder": (0.80, 1.10),
            "LeftArm":       (0.60, 1.16),
            "RightArm":      (0.60, 1.16),
            "LeftForeArm":   (0.58, 1.14),
            "RightForeArm":  (0.58, 1.14),
            "LeftHand":      (0.75, 1.35),
            "RightHand":     (0.75, 1.35),
            "LeftUpLeg":     (0.50, 1.12),
            "RightUpLeg":    (0.50, 1.12),
            "LeftLeg":       (0.48, 1.10),
            "RightLeg":      (0.48, 1.10),
            "LeftFoot":      (0.85, 1.25),
            "RightFoot":     (0.85, 1.25),
            "LeftToeBase":   (0.85, 1.25),
            "RightToeBase":  (0.85, 1.25),
        },
        "head_lift": 5.0,
        "jaw_squash": 0.84,
        "cranium_bulge": 1.10,
        "head_depth": 0.94,
        "eye_scale": 1.30,
        "motion_scale": 0.52,
    },
    "jrpg": {
        "bones": {
            "Hips":          (0.92, 1.06),
            "Spine02":       (0.86, 1.06),
            "Spine01":       (0.86, 1.04),
            "Spine":         (0.95, 1.04),
            "neck":          (0.45, 1.02),
            "Head":          (1.60, 1.60),
            "head_end":      (1.60, 1.60),
            "headfront":     (1.60, 1.60),
            "LeftShoulder":  (0.90, 1.06),
            "RightShoulder": (0.90, 1.06),
            "LeftArm":       (0.74, 1.10),
            "RightArm":      (0.74, 1.10),
            "LeftForeArm":   (0.72, 1.08),
            "RightForeArm":  (0.72, 1.08),
            "LeftHand":      (0.85, 1.22),
            "RightHand":     (0.85, 1.22),
            "LeftUpLeg":     (0.66, 1.06),
            "RightUpLeg":    (0.66, 1.06),
            "LeftLeg":       (0.64, 1.05),
            "RightLeg":      (0.64, 1.05),
            "LeftFoot":      (0.92, 1.15),
            "RightFoot":     (0.92, 1.15),
            "LeftToeBase":   (0.92, 1.15),
            "RightToeBase":  (0.92, 1.15),
        },
        "head_lift": 3.0,
        "jaw_squash": 0.90,
        "cranium_bulge": 1.06,
        "head_depth": 0.97,
        "eye_scale": 1.18,
        "motion_scale": 0.68,
    },
}

COMMON = {
    "eye_radius_in": 0.9,     # full-strength radius around each eye centroid
    "eye_radius_out": 2.2,    # falloff ends here (bone units, ~cm)
    "eye_depth": 1.06,        # how much the socket bulges forward
    "scale_object_root_motion": True,
}

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/home/claude/work/chibi.blend"
PRESET = argv[1] if len(argv) > 1 else "chibi"
P = dict(COMMON)
P.update({k: (dict(v) if isinstance(v, dict) else v)
          for k, v in PRESETS[PRESET].items()})
if len(argv) > 2 and argv[2].strip():
    over = json.loads(argv[2])
    P["bones"].update(over.pop("bones", {}))
    P.update(over)

MESH, RIG = "PF_Tiefling_Bald_Female", "PF_Tiefling_Bald_Female_Rig"
ob, rig = bpy.data.objects[MESH], bpy.data.objects[RIG]
arm, me = rig.data, bpy.data.objects[MESH].data

A2M = rig.matrix_world.inverted() @ ob.matrix_world   # mesh local -> armature
M2A = A2M.inverted()
gname = {g.index: g.name for g in ob.vertex_groups}

# ----------------------------------------------------------------------------
# 1. new rest matrices
# ----------------------------------------------------------------------------
old_M, old_len, order = {}, {}, []


def walk(b):
    old_M[b.name] = b.matrix_local.copy()
    old_len[b.name] = b.length
    order.append(b.name)
    for c in b.children:
        walk(c)


for b in arm.bones:
    if b.parent is None:
        walk(b)
parent_of = {b.name: (b.parent.name if b.parent else None) for b in arm.bones}


def S(name):
    ln, gr = P["bones"].get(name, (1.0, 1.0))
    return Matrix.Diagonal(Vector((gr, ln, gr, 1.0)))


new_M = {}
for name in order:                       # parents first
    p = parent_of[name]
    if p is None:
        new_M[name] = old_M[name].copy()
        continue
    rel = old_M[p].inverted() @ old_M[name]
    nrel = rel.to_3x3().to_4x4()                        # orientation unchanged
    nrel.translation = (S(p) @ rel.translation.to_4d()).to_3d()
    new_M[name] = new_M[p] @ nrel

D = {n: new_M[n] @ S(n) @ old_M[n].inverted() for n in order}

# ----------------------------------------------------------------------------
# 2. find the eyes by sampling the base colour texture
# ----------------------------------------------------------------------------
head_v = {v.index for v in me.vertices
          if any(gname[g.group] == "Head" and g.weight > 0.7 for g in v.groups)}
hz = [(A2M @ me.vertices[i].co).z for i in head_v]
hz_lo, hz_hi = min(hz), max(hz)

eyes = []
img = bpy.data.images.get("PF_BaseColor")
if img and P["eye_scale"] != 1.0:
    W, H = img.size
    px = list(img.pixels)
    uvl = me.uv_layers.active.data
    vuv = {}
    for l in me.loops:
        vuv.setdefault(l.vertex_index, uvl[l.index].uv.copy())
    lo = hz_lo + 0.22 * (hz_hi - hz_lo)
    hi = hz_lo + 0.90 * (hz_hi - hz_lo)
    hits = []
    for vi in head_v:
        p = A2M @ me.vertices[vi].co
        if p.y > -2 or not (lo < p.z < hi):
            continue                       # front of the face only
        uv = vuv.get(vi)
        if uv is None:
            continue
        x = int(min(max(uv.x, 0), 0.999) * W)
        y = int(min(max(uv.y, 0), 0.999) * H)
        i = (y * W + x) * 4
        r, g, b = px[i], px[i + 1], px[i + 2]
        mx, mn = max(r, g, b), min(r, g, b)
        if mx > 0.45 and (mx - mn) / max(mx, 1e-6) < 0.18:   # bright + desat
            hits.append(p)
    for sgn in (1, -1):
        side = [p for p in hits if p.x * sgn > 0.5]
        if len(side) >= 3:
            c = sum(side, Vector((0, 0, 0))) / len(side)
            eyes.append(c)
            print(f"[chibi] eye found n={len(side):3d} "
                  f"({c.x:.2f}, {c.y:.2f}, {c.z:.2f})")
if len(eyes) != 2:
    print("[chibi] eye detection inconclusive - skipping eye pass")
    eyes = []

r_in, r_out, e_s, e_d = (P["eye_radius_in"], P["eye_radius_out"],
                         P["eye_scale"], P["eye_depth"])


def eye_pass(p):
    """inflate the eye region in the ORIGINAL rest space, before the retarget"""
    for c in eyes:
        d = p - c
        r = d.length
        if r >= r_out:
            continue
        t = 1.0 if r <= r_in else 1.0 - (r - r_in) / (r_out - r_in)
        t = t * t * (3 - 2 * t)
        s = 1.0 + (e_s - 1.0) * t
        p = c + Vector((d.x * s, d.y * (1.0 + (e_d - 1.0) * t), d.z * s))
    return p


# ----------------------------------------------------------------------------
# 3. head shaping, in original head-bone space
# ----------------------------------------------------------------------------
head_M = old_M["Head"]
head_Mi = head_M.inverted()
head_span = hz_hi - hz_lo
jaw, dome, depth = P["jaw_squash"], P["cranium_bulge"], P["head_depth"]


def head_shape(v_arm, w):
    if w <= 0.001:
        return v_arm
    l = head_Mi @ v_arm
    t = max(0.0, min(1.0, l.y / head_span))
    t = t * t * (3 - 2 * t)
    g = 1.0 + ((jaw + (dome - jaw) * t) - 1.0) * w
    l.x *= g
    l.z *= g * (1.0 + (depth - 1.0) * w)
    return head_M @ l


# ----------------------------------------------------------------------------
# 4. deform
# ----------------------------------------------------------------------------
new_co = []
for v in me.vertices:
    p = eye_pass(A2M @ v.co)
    tot = sum(g.weight for g in v.groups) or 1.0
    acc = Vector((0.0, 0.0, 0.0))
    hw = 0.0
    for g in v.groups:
        w = g.weight / tot
        acc += (D[gname[g.group]] @ p) * w
        if gname[g.group] == "Head":
            hw = w
    acc = head_shape(acc, hw)
    acc.z += P["head_lift"] * hw
    new_co.append(acc)

# re-ground
dz = -min(p.z for p in new_co)
for p in new_co:
    p.z += dz
for n in order:
    new_M[n].translation.z += dz

hi_z = max(p.z for p in new_co)
head_lo = min(new_co[i].z for i in head_v)
print(f"[chibi/{PRESET}] height {hi_z:.1f}u  head {hi_z - head_lo:.1f}u  "
      f"=> {hi_z / (hi_z - head_lo):.2f} heads tall  (ground shift {dz:.1f})")

for i, v in enumerate(me.vertices):
    v.co = M2A @ new_co[i]
me.update()

# ----------------------------------------------------------------------------
# 5. write the rest skeleton
# ----------------------------------------------------------------------------
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
for eb in arm.edit_bones:
    eb.use_connect = False        # connected children would snap back to the tail
for name in order:
    eb = arm.edit_bones[name]
    eb.matrix = new_M[name]
    eb.length = max(old_len[name] * P["bones"].get(name, (1.0, 1.0))[0], 1e-4)
bpy.ops.object.mode_set(mode="OBJECT")

# ----------------------------------------------------------------------------
# 6. rescale Hips translation to match the shorter legs
# ----------------------------------------------------------------------------
ms = P["motion_scale"]
if ms != 1.0:
    n = 0
    for act in bpy.data.actions:
        for layer in act.layers:
            for strip in layer.strips:
                for cbag in strip.channelbags:
                    for fc in cbag.fcurves:
                        dp = fc.data_path
                        if dp != 'pose.bones["Hips"].location' and not (
                                dp == "location" and P["scale_object_root_motion"]):
                            continue
                        n += 1
                        for k in fc.keyframe_points:
                            k.co[1] *= ms
                            k.handle_left[1] *= ms
                            k.handle_right[1] *= ms
    print(f"[chibi] scaled {n} translation fcurves by {ms}")

bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print(f"[chibi] wrote {OUT}")
