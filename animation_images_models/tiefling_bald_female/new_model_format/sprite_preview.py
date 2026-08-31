"""preview.py -- render turntable-ish sprite previews.
blender -b file.blend --python preview.py -- OUTDIR TAG "Action:frame,Action:frame" res samples
"""
import bpy, sys, math, os
from mathutils import Vector, Euler

a = sys.argv[sys.argv.index("--") + 1:]
OUT, TAG, SHOTS = a[0], a[1], a[2]
RES = int(a[3]) if len(a) > 3 else 320
SAMP = int(a[4]) if len(a) > 4 else 24

rig = bpy.data.objects["PF_Tiefling_Bald_Female_Rig"]
mesh = bpy.data.objects["PF_Tiefling_Bald_Female"]
sc = bpy.context.scene

# bounds of the current mesh in world space
co = [mesh.matrix_world @ Vector(c) for c in mesh.bound_box]
zmin, zmax = min(c.z for c in co), max(c.z for c in co)
h = zmax - zmin
cz = (zmin + zmax) / 2

# --- world / lights ---
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.13, 0.14, 0.18, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sc.world = w

for name, rot, e in (("key", (55, 0, 40), 4.0), ("fill", (70, 0, -60), 1.6),
                     ("rim", (110, 0, 190), 3.0)):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = e
    ld.angle = 0.5
    lo = bpy.data.objects.new(name, ld)
    lo.rotation_euler = Euler([math.radians(x) for x in rot])
    sc.collection.objects.link(lo)

# --- ortho camera on an empty pivot ---
cam_d = bpy.data.cameras.new("cam")
cam_d.type = "ORTHO"
cam_d.ortho_scale = h * 1.18
cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam

sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMP
sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.film_transparent = False

VIEWS = {"front": 0.0, "three": 40.0, "side": 90.0}
MODE = a[5] if len(a) > 5 else ""
ZOOM = MODE == "face"
if ZOOM:
    VIEWS = {"faceF": 0.0, "faceT": 35.0}
elif MODE == "front":
    VIEWS = {"front": 0.0}
elif MODE == "three":
    VIEWS = {"three": 40.0}


hz = max(c.z for c in co)
def place(deg):
    r = math.radians(deg)
    d = h * 3.0
    tz = cz
    if ZOOM:
        tz = zmin + (zmax - zmin) * 0.86
        cam_d.ortho_scale = h * 0.42
    cam.location = Vector((math.sin(r) * d, -math.cos(r) * d, tz))
    cam.rotation_euler = Euler((math.radians(90), 0, r))


for shot in SHOTS.split(","):
    act_name, frame = shot.split(":")
    frame = int(frame)
    if act_name != "REST":
        act = bpy.data.actions[act_name]
        if not rig.animation_data:
            rig.animation_data_create()
        rig.animation_data.action = act
        if act.slots:
            rig.animation_data.action_slot = act.slots[0]
        sc.frame_set(frame)
    else:
        if rig.animation_data:
            rig.animation_data.action = None
        for pb in rig.pose.bones:
            pb.matrix_basis.identity()
        sc.frame_set(1)
    bpy.context.view_layer.update()
    for vn, deg in VIEWS.items():
        place(deg)
        sc.render.filepath = os.path.join(OUT, f"{TAG}_{act_name}_{frame}_{vn}.png")
        bpy.ops.render.render(write_still=True)
        print("WROTE", sc.render.filepath)
