"""3D simulyatsiya: bir joyda turadigan, ikki qo'lli robot mahsulotlarni rangiga qarab saralaydi.

Faqat standart kutubxona (tkinter) kerak. PyCharm'da shu faylni Run qiling.

Sxema (tepdan ko'rinish):
                 KIRISH konveyeri (mahsulotlar keladi)
                        |  |
    QIZIL konveyer      |  |      KO'K konveyer
         |  |      <- [chap qo'l] ROBOT [o'ng qo'l] ->      |  |

Chap qo'l qizil mahsulotni chap konveyerga, o'ng qo'l ko'k mahsulotni o'ng konveyerga qo'yadi.

Boshqaruv:  sichqoncha bilan sudrash - aylantirish,  g'ildirak - yaqinlashtirish,
            SPACE - pauza,  R - kamerani tiklash.
"""
import math
import random
import tkinter as tk

W, H = 1000, 680
FPS = 40
FOCAL = 950

# --- vektor yordamchilari ------------------------------------------------


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def length(a): return math.sqrt(dot(a, a))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    n = length(a)
    return (a[0] / n, a[1] / n, a[2] / n)


LIGHT = norm((-0.4, 1.0, 0.6))

# --- sahna o'lchamlari ---------------------------------------------------

BELT_TOP = 1.0                 # konveyer yuzasi balandligi
ITEM_H = 0.25                  # mahsulot (kub) yarim o'lchami
ITEM_Y = BELT_TOP + ITEM_H
PICK_Z = -2.6                  # mahsulot to'xtaydigan joy
OUT_X = 3.6                    # chiqish konveyerlarining x koordinatasi
BELT_W = 1.3
SPEED = 0.035                  # konveyer tezligi (birlik/kadr)
ARM_SPEED = 0.10
L1 = L2 = 2.3                  # qo'l bo'g'inlari uzunligi
WRIST_UP = 0.5                 # panja mahsulot markazidan qancha yuqorida

COLORS = {"red": (229, 57, 53), "blue": (30, 136, 229)}
STEEL = (120, 130, 140)
DARK = (55, 62, 70)


# --- 3D shakllar (poligonlar ro'yxatiga qo'shiladi) ----------------------

def box(prims, c, half, color, layer=2, axes=((1, 0, 0), (0, 1, 0), (0, 0, 1))):
    for i in range(3):
        j, k = (i + 1) % 3, (i + 2) % 3
        for s in (1, -1):
            n = mul(axes[i], s)
            fc = add(c, mul(n, half[i]))
            pts = []
            for sj, sk in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                pts.append(add(fc, add(mul(axes[j], sj * half[j]), mul(axes[k], sk * half[k]))))
            prims.append(("poly", layer, pts, color, n))


def link(prims, p0, p1, t, color, layer=2):
    """p0 dan p1 gacha qalinligi t bo'lgan sterjen."""
    d = sub(p1, p0)
    n = length(d)
    if n < 1e-6:
        return
    a = mul(d, 1 / n)
    ref = (0, 1, 0) if abs(a[1]) < 0.95 else (1, 0, 0)
    b = norm(cross(a, ref))
    c = cross(a, b)
    box(prims, mul(add(p0, p1), 0.5), (n / 2, t / 2, t / 2), color, layer, (a, b, c))


def ball(prims, c, r, color, layer=2):
    prims.append(("ball", layer, c, r, color))


def two_link_ik(s, w):
    """Yelka s va panja w berilsa, tirsak nuqtasini qaytaradi (tirsak tepada)."""
    v = sub(w, s)
    d = max(0.3, min(length(v), L1 + L2 - 1e-3))
    h = math.hypot(v[0], v[2])
    elev = math.atan2(v[1], h)
    cos_a = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    a = math.acos(max(-1.0, min(1.0, cos_a)))
    el = elev + a
    ux, uz = (v[0] / h, v[2] / h) if h > 1e-6 else (1.0, 0.0)
    return (s[0] + L1 * math.cos(el) * ux, s[1] + L1 * math.sin(el), s[2] + L1 * math.cos(el) * uz)


# --- mantiq --------------------------------------------------------------

class Item:
    def __init__(self, color, z):
        self.color = color
        self.pos = [0.0, ITEM_Y, z]
        self.state = "in"          # in | held | out
        self.claimed = False


class Arm:
    def __init__(self, color, side):
        self.color = color
        self.side = side           # -1 chap, +1 o'ng
        self.shoulder = (side * 1.0, 1.9, 0.0)
        self.home = (side * 2.0, 2.2, -1.4)
        self.tip = list(self.home)  # ushlangan mahsulot markazi
        self.grip = 0.5            # panja ochiqligi
        self.grip_goal = 0.5
        self.item = None
        self.queue = []
        self.pause = 0

    @property
    def busy(self):
        return bool(self.queue)

    def start(self, item):
        ix, iz = item.pos[0], item.pos[2]
        dx = self.side * OUT_X
        up = 2.6
        self.queue = [
            ((ix, up, iz), None),
            ((ix, ITEM_Y, iz), "grab"),
            ((ix, up, iz), None),
            ((dx, up, iz), None),
            ((dx, ITEM_Y, iz), "release"),
            ((dx, up, iz), None),
            (self.home, None),
        ]
        self.target_item = item

    def update(self, world):
        self.grip += max(-0.02, min(0.02, self.grip_goal - self.grip))
        if self.pause > 0:
            self.pause -= 1
        elif self.queue:
            goal, action = self.queue[0]
            d = sub(goal, tuple(self.tip))
            n = length(d)
            if n <= ARM_SPEED:
                self.tip = list(goal)
                self.queue.pop(0)
                if action == "grab":
                    self.item = self.target_item
                    self.item.state = "held"
                    self.grip_goal = 0.3
                    self.pause = 12
                elif action == "release":
                    self.item.state = "out"
                    world.sorted[self.color] += 1
                    self.item = None
                    self.grip_goal = 0.5
                    self.pause = 12
            else:
                self.tip = [self.tip[i] + d[i] / n * ARM_SPEED for i in range(3)]
        if self.item:
            self.item.pos = list(self.tip)

    def build(self, prims):
        s = self.shoulder
        w = (self.tip[0], self.tip[1] + WRIST_UP, self.tip[2])
        e = two_link_ik(s, w)
        link(prims, s, e, 0.40, (240, 140, 20))
        link(prims, e, w, 0.32, (250, 165, 40))
        ball(prims, e, 0.28, STEEL)
        ball(prims, w, 0.2, STEEL)
        # panja: yassi plastina va ikkita barmoq
        hv = (w[0] - s[0], w[2] - s[2])
        hn = math.hypot(*hv) or 1.0
        fwd = (hv[0] / hn, 0.0, hv[1] / hn)
        perp = (-fwd[2], 0.0, fwd[0])
        box(prims, add(w, (0, -0.08, 0)), (0.42, 0.06, 0.22), DARK, 2, (perp, (0, 1, 0), fwd))
        for sg in (1, -1):
            top = add(w, add((0, -0.1, 0), mul(perp, sg * self.grip)))
            link(prims, top, add(top, (0, -0.55, 0)), 0.1, DARK)


class World:
    def __init__(self):
        self.reset()

    def reset(self):
        self.items = []
        self.sorted = {"red": 0, "blue": 0}
        self.arms = {"red": Arm("red", -1), "blue": Arm("blue", +1)}
        self.t = 0
        self.belt_off = 0.0

    def update(self):
        self.t += 1
        self.belt_off += SPEED

        # yangi mahsulot
        if self.t % 55 == 0:
            if not any(i.state == "in" and i.pos[2] < -9.6 + 1.0 for i in self.items):
                self.items.append(Item(random.choice(list(COLORS)), -9.6))

        # kirish konveyeri: mahsulotlar robotga qarab yuradi va to'xtaydi
        ins = sorted((i for i in self.items if i.state == "in"), key=lambda i: -i.pos[2])
        limit = PICK_Z
        for it in ins:
            it.pos[2] = min(it.pos[2] + SPEED, limit)
            limit = it.pos[2] - 0.85

        # chiqish konveyerlari mahsulotni olib ketadi
        for it in self.items:
            if it.state == "out":
                it.pos[2] -= SPEED
        self.items = [i for i in self.items if i.state != "out" or i.pos[2] > -9.0]

        # navbatdagi mahsulotni rangiga mos qo'l oladi
        if ins and abs(ins[0].pos[2] - PICK_Z) < 1e-6 and not ins[0].claimed:
            arm = self.arms[ins[0].color]
            if not arm.busy:
                ins[0].claimed = True
                arm.start(ins[0])

        for arm in self.arms.values():
            arm.update(self)

    # --- sahna geometriyasi ---
    def belt(self, prims, x, z0, z1, direction, rail_color):
        ln = z1 - z0
        zc = (z0 + z1) / 2
        box(prims, (x, BELT_TOP - 0.15, zc), (BELT_W / 2, 0.15, ln / 2), (62, 70, 78), 0)
        for sx in (-1, 1):
            for z in (z0 + 0.3, z1 - 0.3):
                box(prims, (x + sx * (BELT_W / 2 - 0.1), 0.35, z), (0.07, 0.35, 0.07), DARK, 0)
            box(prims, (x + sx * (BELT_W / 2 + 0.05), BELT_TOP + 0.05, zc), (0.07, 0.17, ln / 2), rail_color, 2)
        # harakatlanuvchi chiziqlar
        step = 0.8
        for k in range(int(ln / step) + 1):
            z = z0 + (k * step + direction * self.belt_off) % ln
            a, b = max(z0, z - 0.08), min(z1, z + 0.08)
            hw = BELT_W / 2
            prims.append(("poly", 1, [(x - hw, BELT_TOP + 0.003, a), (x + hw, BELT_TOP + 0.003, a),
                                      (x + hw, BELT_TOP + 0.003, b), (x - hw, BELT_TOP + 0.003, b)],
                          (88, 98, 108), (0, 1, 0)))

    def build(self):
        prims = []
        # pol
        f = 10
        prims.append(("poly", -2, [(-f, 0, -f - 4), (f, 0, -f - 4), (f, 0, f - 4), (-f, 0, f - 4)],
                      (205, 210, 215), (0, 1, 0)))
        for g in range(-f, f + 1, 2):
            prims.append(("line", -1, (g, 0.002, -f - 4), (g, 0.002, f - 4), (185, 190, 196)))
            prims.append(("line", -1, (-f, 0.002, g - 4), (f, 0.002, g - 4), (185, 190, 196)))

        # konveyerlar
        self.belt(prims, 0.0, -10.0, -2.0, +1, (140, 150, 160))
        self.belt(prims, -OUT_X, -9.0, -0.6, -1, COLORS["red"])
        self.belt(prims, OUT_X, -9.0, -0.6, -1, COLORS["blue"])

        # robot (joyida turadi)
        box(prims, (0, 0.3, 0), (1.2, 0.3, 1.0), DARK)
        box(prims, (0, 1.0, 0), (0.35, 0.5, 0.35), STEEL)
        box(prims, (0, 1.9, 0), (0.85, 0.4, 0.45), (225, 230, 235))
        box(prims, (0, 2.6, 0), (0.32, 0.26, 0.3), (225, 230, 235))
        for ex in (-0.13, 0.13):
            box(prims, (ex, 2.64, -0.31), (0.06, 0.06, 0.012), (20, 20, 20))
        for arm in self.arms.values():
            ball(prims, arm.shoulder, 0.34, COLORS[arm.color])
            arm.build(prims)

        # mahsulotlar
        for it in self.items:
            box(prims, tuple(it.pos), (ITEM_H,) * 3, COLORS[it.color])
        return prims


# --- ko'rinish (kamera + chizish) ----------------------------------------

class Viewer:
    def __init__(self, root):
        self.root = root
        root.title("3D robot - rang bo'yicha saralash")
        self.cv = tk.Canvas(root, width=W, height=H, bg="#b0bec5", highlightthickness=0)
        self.cv.pack()
        self.world = World()
        self.paused = False
        self.reset_camera()

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<MouseWheel>", lambda e: self.zoom(0.9 if e.delta > 0 else 1.1))
        self.cv.bind("<Button-4>", lambda e: self.zoom(0.9))
        self.cv.bind("<Button-5>", lambda e: self.zoom(1.1))
        root.bind("<space>", lambda e: setattr(self, "paused", not self.paused))
        root.bind("<r>", lambda e: self.reset_camera())
        self.tick()

    def reset_camera(self):
        self.yaw, self.pitch, self.dist = 0.45, 0.55, 19.0
        self.target = (0.0, 1.2, -4.0)

    def on_press(self, e):
        self.last = (e.x, e.y)

    def on_drag(self, e):
        self.yaw -= (e.x - self.last[0]) * 0.008
        self.pitch = max(0.08, min(1.45, self.pitch + (e.y - self.last[1]) * 0.008))
        self.last = (e.x, e.y)

    def zoom(self, k):
        self.dist = max(6.0, min(45.0, self.dist * k))

    def setup_camera(self):
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        self.cpos = add(self.target, (self.dist * cp * math.sin(self.yaw), self.dist * sp,
                                      self.dist * cp * math.cos(self.yaw)))
        self.fwd = norm(sub(self.target, self.cpos))
        self.right = norm(cross(self.fwd, (0, 1, 0)))
        self.upv = cross(self.right, self.fwd)

    def to_cam(self, p):
        r = sub(p, self.cpos)
        return dot(r, self.right), dot(r, self.upv), dot(r, self.fwd)

    def scr(self, c):
        return W / 2 + FOCAL * c[0] / c[2], H / 2 - FOCAL * c[1] / c[2]

    @staticmethod
    def hexcol(c, k=1.0):
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(v * k))) for v in c)

    def render(self):
        cv = self.cv
        cv.delete("all")
        self.setup_camera()
        draw = []
        for pr in self.world.build():
            kind = pr[0]
            if kind == "poly":
                _, layer, pts, col, n = pr
                cam = [self.to_cam(p) for p in pts]
                if any(c[2] < 0.3 for c in cam):
                    continue
                cen = (sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4, sum(p[2] for p in pts) / 4)
                k = 0.5 + 0.5 * max(0.0, dot(n, LIGHT))
                draw.append((layer, -length(sub(cen, self.cpos)), "poly",
                             [self.scr(c) for c in cam], self.hexcol(col, k)))
            elif kind == "ball":
                _, layer, c, r, col = pr
                cc = self.to_cam(c)
                if cc[2] < 0.3:
                    continue
                x, y = self.scr(cc)
                draw.append((layer, -length(sub(c, self.cpos)), "ball", (x, y, r * FOCAL / cc[2]),
                             self.hexcol(col)))
            else:
                _, layer, p0, p1, col = pr
                a, b = self.to_cam(p0), self.to_cam(p1)
                if a[2] < 0.3 or b[2] < 0.3:
                    continue
                draw.append((layer, -length(sub(p0, self.cpos)), "line", self.scr(a) + self.scr(b),
                             self.hexcol(col)))

        draw.sort(key=lambda t: (t[0], t[1]))
        for _, _, kind, geom, col in draw:
            if kind == "poly":
                cv.create_polygon(geom, fill=col, outline="#263238")
            elif kind == "ball":
                x, y, r = geom
                cv.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="#263238")
            else:
                cv.create_line(*geom, fill=col)

        # yozuvlar
        for text, p, col in (("KIRISH", (0, 2.2, -10.0), "black"),
                             ("QIZIL", (-OUT_X, 2.2, -0.6), self.hexcol(COLORS["red"])),
                             ("KO'K", (OUT_X, 2.2, -0.6), self.hexcol(COLORS["blue"]))):
            c = self.to_cam(p)
            if c[2] > 0.3:
                x, y = self.scr(c)
                cv.create_text(x, y, text=text, fill=col, font=("Arial", 12, "bold"))
        s = self.world.sorted
        cv.create_text(W / 2, 22, font=("Arial", 14, "bold"),
                       text=f"Saralandi  -  Qizil: {s['red']}    Ko'k: {s['blue']}")
        cv.create_text(W / 2, H - 14, font=("Arial", 10), fill="#37474f",
                       text="Sichqoncha: aylantirish  |  G'ildirak: zoom  |  SPACE: pauza  |  R: kamerani tiklash")

    def tick(self):
        if not self.paused:
            self.world.update()
        self.render()
        self.root.after(1000 // FPS, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    Viewer(root)
    root.mainloop()
