"""3D simulyatsiya: sanoat uslubidagi ikki qo'lli robot mahsulotlarni rangiga qarab saralaydi.

PyCharm'da shu faylni Run qiling.  Tiniq (anti-alias) grafika uchun Pillow kerak:
    pip install pillow
Pillow bo'lmasa ham dastur ishlaydi, faqat grafika biroz xomroq bo'ladi.

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
import time
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except ImportError:                     # Pillow yo'q - oddiy canvas bilan chizamiz
    HAVE_PIL = False

W, H = 1100, 720
SS = 2                                  # anti-alias: ichki o'lcham koeffitsiyenti (Pillow bilan)
FOCAL = 1050
NEAR = 0.3
SIM_HZ = 40                             # simulyatsiya chastotasi (chizish tezligidan mustaqil)

# --- vektor yordamchilari ------------------------------------------------


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def length(a): return math.sqrt(dot(a, a))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    n = length(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


KEY_LIGHT = norm((-0.45, 1.0, 0.55))
FILL_LIGHT = norm((0.7, 0.35, -0.6))

# --- sahna o'lchamlari ---------------------------------------------------

BELT_TOP = 1.0                 # konveyer yuzasi balandligi
ITEM_H = 0.25                  # mahsulot (karobka) yarim o'lchami
ITEM_Y = BELT_TOP + ITEM_H
PICK_Z = -2.6                  # mahsulot to'xtaydigan joy
OUT_X = 3.6                    # chiqish konveyerlarining x koordinatasi
BELT_W = 1.3
SPEED = 0.035                  # konveyer tezligi (birlik/qadam)
ARM_SPEED = 0.10
L1 = L2 = 2.3                  # qo'l bo'g'inlari uzunligi
WRIST_UP = 0.9                 # panja markazi mahsulot markazidan qancha yuqorida
SHOULDER_Y = 2.4

COLORS = {"red": (222, 48, 44), "blue": (28, 120, 226)}
YELLOW = (250, 196, 0)         # sanoat robotining klassik sariq rangi
DARK = (46, 49, 54)
STEEL = (170, 176, 184)
LIGHT_GREY = (206, 210, 214)
BLACK = (24, 24, 26)


# --- 3D shakllar: poligonlar ro'yxatiga qo'shiladi ------------------------
# ("poly", qatlam, nuqtalar, rang, normal, chetlari, yaltiroqlik, bias)

def poly(prims, layer, pts, color, n, edge=True, spec=0.2, bias=0.0):
    prims.append(("poly", layer, pts, color, n, edge, spec, bias))


def box(prims, c, half, color, layer=2, axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)), spec=0.2):
    for i in range(3):
        j, k = (i + 1) % 3, (i + 2) % 3
        for s in (1, -1):
            n = mul(axes[i], s)
            fc = add(c, mul(n, half[i]))
            pts = [add(fc, add(mul(axes[j], sj * half[j]), mul(axes[k], sk * half[k])))
                   for sj, sk in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
            poly(prims, layer, pts, color, n, True, spec)


def link(prims, p0, p1, t, color, layer=2):
    """p0 dan p1 gacha qalinligi t bo'lgan to'g'ri to'rtburchak sterjen."""
    d = sub(p1, p0)
    n = length(d)
    if n < 1e-6:
        return
    a = mul(d, 1 / n)
    ref = (0, 1, 0) if abs(a[1]) < 0.95 else (1, 0, 0)
    b = norm(cross(a, ref))
    c = cross(a, b)
    box(prims, mul(add(p0, p1), 0.5), (n / 2, t / 2, t / 2), color, layer, (a, b, c))


def cyl(prims, p0, p1, r0, color, r1=None, n=14, layer=2, caps=True, spec=0.55):
    """p0 dan p1 gacha silindr (r1 berilsa - kesik konus)."""
    r1 = r0 if r1 is None else r1
    d = sub(p1, p0)
    ln = length(d)
    if ln < 1e-6:
        return
    a = mul(d, 1 / ln)
    ref = (0, 1, 0) if abs(a[1]) < 0.95 else (1, 0, 0)
    u = norm(cross(a, ref))
    v = cross(a, u)
    cs = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    ring0 = [add(p0, add(mul(u, c * r0), mul(v, s * r0))) for c, s in cs]
    ring1 = [add(p1, add(mul(u, c * r1), mul(v, s * r1))) for c, s in cs]
    slope = (r0 - r1) / ln
    for i in range(n):
        j = (i + 1) % n
        am = 2 * math.pi * (i + 0.5) / n
        nrm = norm(add(add(mul(u, math.cos(am)), mul(v, math.sin(am))), mul(a, slope)))
        poly(prims, layer, [ring0[i], ring0[j], ring1[j], ring1[i]], color, nrm, False, spec)
    if caps:
        poly(prims, layer, ring0, color, mul(a, -1), False, spec)
        poly(prims, layer, ring1, color, a, False, spec)


def ball(prims, c, r, color, layer=2):
    prims.append(("ball", layer, c, r, color))


def cable(prims, p0, p1, sag, segs=6, t=0.08, color=BLACK):
    """Ikki nuqta orasida egilgan shlang/kabel."""
    pts = []
    for i in range(segs + 1):
        u = i / segs
        p = add(mul(p0, 1 - u), mul(p1, u))
        pts.append(add(p, (0, sag * math.sin(math.pi * u), 0)))
    for a, b in zip(pts, pts[1:]):
        link(prims, a, b, t, color)


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
        self.shoulder = (side * 1.0, SHOULDER_Y, 0.0)
        self.home = (side * 2.0, 2.2, -1.4)
        self.tip = list(self.home)  # ushlangan mahsulot markazi
        self.grip = 0.5            # panja ochiqligi
        self.grip_goal = 0.5
        self.item = None
        self.target_item = None
        self.queue = []
        self.pause = 0

    @property
    def busy(self):
        return bool(self.queue)

    def start(self, item):
        ix, iz = item.pos[0], item.pos[2]
        dx = self.side * OUT_X
        up = 2.6
        self.target_item = item
        self.queue = [
            ((ix, up, iz), None),
            ((ix, ITEM_Y, iz), "grab"),
            ((ix, up, iz), None),
            ((dx, up, iz), None),
            ((dx, ITEM_Y, iz), "release"),
            ((dx, up, iz), None),
            (self.home, None),
        ]

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
                    self.pause = 14
                elif action == "release":
                    self.item.state = "out"
                    world.sorted[self.color] += 1
                    self.item = None
                    self.grip_goal = 0.5
                    self.pause = 14
            else:
                self.tip = [self.tip[i] + d[i] / n * ARM_SPEED for i in range(3)]
        if self.item:
            self.item.pos = list(self.tip)

    def build(self, prims):
        """Sanoat (6 o'qli) qo'li: turret, yelka, tirsak, bilak, panja va gripper."""
        s = self.shoulder
        w = (self.tip[0], self.tip[1] + WRIST_UP, self.tip[2])
        e = two_link_ik(s, w)
        up = (0, 1, 0)
        hv = (w[0] - s[0], w[2] - s[2])
        hn = math.hypot(*hv) or 1.0
        fwd = (hv[0] / hn, 0.0, hv[1] / hn)
        perp = (-fwd[2], 0.0, fwd[0])               # J2 / J3 o'qi yo'nalishi
        axes = (perp, up, fwd)
        led = COLORS[self.color]

        # J1: turret + rangli indikator halqa + aylanuvchi yelka bloki
        cyl(prims, (s[0], 1.85, s[2]), (s[0], 2.02, s[2]), 0.58, DARK, n=20)
        cyl(prims, (s[0], 2.02, s[2]), (s[0], 2.08, s[2]), 0.6, led, n=20)
        box(prims, add((s[0], 2.28, s[2]), mul(fwd, -0.18)), (0.44, 0.22, 0.4), YELLOW, 2, axes)
        # J2: yelka reduktori
        cyl(prims, sub(s, mul(perp, 0.56)), add(s, mul(perp, 0.56)), 0.44, YELLOW, n=18)
        for sg in (1, -1):
            cyl(prims, add(s, mul(perp, sg * 0.56)), add(s, mul(perp, sg * 0.63)), 0.3, DARK, n=14)
        # yuqori qo'l
        cyl(prims, s, e, 0.36, YELLOW, r1=0.28, n=16)
        link(prims, add(s, (0, 0.34, 0)), add(e, (0, 0.27, 0)), 0.1, DARK)   # kabel kanali
        # J3: tirsak
        cyl(prims, sub(e, mul(perp, 0.44)), add(e, mul(perp, 0.44)), 0.34, YELLOW, n=18)
        for sg in (1, -1):
            cyl(prims, add(e, mul(perp, sg * 0.44)), add(e, mul(perp, sg * 0.5)), 0.24, DARK, n=14)
        # bilak
        dirf = norm(sub(w, e))
        wb = sub(w, mul(dirf, 0.42))
        cyl(prims, e, wb, 0.27, YELLOW, r1=0.2, n=16)
        # J4: bilak aylanishi, J5: panja egilishi
        cyl(prims, wb, sub(w, mul(dirf, 0.12)), 0.2, DARK, n=14)
        cyl(prims, sub(w, mul(perp, 0.24)), add(w, mul(perp, 0.24)), 0.2, YELLOW, n=14)
        for sg in (1, -1):
            cyl(prims, add(w, mul(perp, sg * 0.24)), add(w, mul(perp, sg * 0.29)), 0.13, DARK, n=12)
        # J6 flantsi va gripper bilan mahkamlash plitasi
        cyl(prims, w, sub(w, (0, 0.12, 0)), 0.17, STEEL, n=14)
        cyl(prims, sub(w, (0, 0.12, 0)), sub(w, (0, 0.19, 0)), 0.25, DARK, n=16)
        # pnevmatik gripper
        box(prims, sub(w, (0, 0.3, 0)), (0.4, 0.11, 0.2), (70, 76, 84), 2, axes)
        box(prims, sub(w, (0, 0.3, 0)), (0.405, 0.025, 0.205), (30, 120, 220), 2, axes)
        box(prims, sub(w, (0, 0.44, 0)), (0.38, 0.03, 0.12), STEEL, 2, axes)
        for sg in (1, -1):
            fit = add(w, mul(perp, sg * 0.24))
            cyl(prims, sub(fit, (0, 0.18, 0)), sub(fit, (0, 0.06, 0)), 0.035, STEEL, n=8, spec=0.8)
            # barmoqlar (rezina pad bilan)
            fx = add(w, mul(perp, sg * self.grip))
            box(prims, sub(fx, (0, 0.44, 0)), (0.1, 0.04, 0.15), STEEL, 2, axes)
            box(prims, sub(fx, (0, 0.78, 0)), (0.05, 0.34, 0.14), (60, 66, 74), 2, axes)
            pad = add(fx, mul(perp, -sg * 0.05))
            box(prims, sub(pad, (0, 0.9, 0)), (0.02, 0.2, 0.12), BLACK, 2, axes, spec=0.05)
        # pnevmatik shlang va kabel
        cable(prims, add(s, (0, 0.5, 0)), add(e, (0, 0.38, 0)), 0.22)
        cable(prims, add(e, (0, 0.38, 0)), add(w, add(mul(perp, 0.24), (0, -0.2, 0))), 0.3)


class World:
    def __init__(self):
        self.static = self.build_static()
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

    # --- statik geometriya (bir marta quriladi) ---
    @staticmethod
    def belt_static(prims, x, z0, z1, rail_color):
        ln = z1 - z0
        zc = (z0 + z1) / 2
        hw = BELT_W / 2
        box(prims, (x, BELT_TOP - 0.1, zc), (hw, 0.1, ln / 2), (58, 64, 72), 0, spec=0.1)
        for sx in (-1, 1):
            box(prims, (x + sx * (hw - 0.08), 0.74, zc), (0.07, 0.14, ln / 2), STEEL, 0)       # ramka to'sinlari
            box(prims, (x + sx * (hw + 0.05), BELT_TOP + 0.08, zc), (0.06, 0.18, ln / 2), rail_color, 2)
            for z in (z0 + 0.35, zc, z1 - 0.35):
                box(prims, (x + sx * (hw - 0.08), 0.35, z), (0.06, 0.35, 0.06), DARK, 0)       # oyoqlar
                box(prims, (x + sx * (hw - 0.08), 0.02, z), (0.14, 0.02, 0.14), STEEL, 0)      # tag plita
        for z in (z0 + 0.35, zc, z1 - 0.35):
            box(prims, (x, 0.3, z), (hw - 0.08, 0.025, 0.025), DARK, 0)                        # ko'ndalang tortqi
        for z in (z0 + 0.02, z1 - 0.02):                                                       # uchlardagi barabanlar
            cyl(prims, (x - hw, BELT_TOP - 0.17, z), (x + hw, BELT_TOP - 0.17, z), 0.2, STEEL, n=16, layer=0)
        # motor-reduktor
        mx = x + (hw + 0.45)
        box(prims, (mx, 0.78, z1 - 0.5), (0.26, 0.26, 0.4), DARK, 2)
        cyl(prims, (mx - 0.26, 0.78, z1 - 0.5), (mx - 0.5, 0.78, z1 - 0.5), 0.14, STEEL, n=12)

    def build_static(self):
        prims = []
        # pol, soyalar va xavfsizlik chizig'i
        f = 16
        poly(prims, -3, [(-f, 0, -f - 4), (f, 0, -f - 4), (f, 0, f - 4), (-f, 0, f - 4)],
             (176, 181, 186), (0, 1, 0), False, 0.0)
        for g in range(-f, f + 1, 2):
            prims.append(("line", -2.5, (g, 0.002, -f - 4), (g, 0.002, f - 4), (164, 169, 175)))
            prims.append(("line", -2.5, (-f, 0.002, g - 4), (f, 0.002, g - 4), (164, 169, 175)))
        for x0, x1, z0, z1 in ((-6.4, 6.4, -10.8, -10.5), (-6.4, 6.4, 1.8, 2.1),
                               (-6.4, -6.1, -10.8, 2.1), (6.1, 6.4, -10.8, 2.1)):
            poly(prims, -2, [(x0, 0.004, z0), (x1, 0.004, z0), (x1, 0.004, z1), (x0, 0.004, z1)],
                 (240, 190, 0), (0, 1, 0), False, 0.0)
        for cx, cz, hx, hz in ((0, 0, 1.6, 1.25), (0, -5.5, 1.0, 4.9), (-OUT_X, -4.8, 1.1, 4.6),
                               (OUT_X, -4.8, 1.1, 4.6)):                               # yumshoq soyalar
            poly(prims, -2.2, [(cx - hx, 0.003, cz - hz), (cx + hx, 0.003, cz - hz),
                               (cx + hx, 0.003, cz + hz), (cx - hx, 0.003, cz + hz)],
                 (150, 155, 161), (0, 1, 0), False, 0.0)

        # konveyerlar
        self.belt_static(prims, 0.0, -10.0, -2.0, (150, 158, 168))
        self.belt_static(prims, -OUT_X, -9.0, -0.6, COLORS["red"])
        self.belt_static(prims, OUT_X, -9.0, -0.6, COLORS["blue"])

        # robot asosi: plita, boltlar, pedestal, bel to'sini
        box(prims, (0, 0.125, 0), (1.5, 0.125, 1.15), DARK)
        for bx in (-1.25, 1.25):
            for bz in (-0.9, 0.9):
                cyl(prims, (bx, 0.25, bz), (bx, 0.33, bz), 0.1, STEEL, n=6, spec=0.8)
        cyl(prims, (0, 0.25, 0), (0, 0.42, 0), 0.9, DARK, n=28)
        cyl(prims, (0, 0.42, 0), (0, 1.5, 0), 0.68, LIGHT_GREY, r1=0.6, n=28)
        cyl(prims, (0, 1.5, 0), (0, 1.58, 0), 0.7, DARK, n=28)
        box(prims, (0, 1.68, 0), (1.5, 0.12, 0.55), LIGHT_GREY)
        box(prims, (0, 1.68, -0.552), (1.2, 0.04, 0.005), COLORS["blue"], spec=0.1)
        box(prims, (0, 1.3, -0.62), (0.07, 0.5, 0.07), BLACK)                              # kabel kanali
        # kamera moduli (vizual sensor) - rangni aniqlaydi
        cyl(prims, (0, 1.78, -0.2), (0, 2.7, -0.2), 0.1, STEEL, n=10)
        box(prims, (0, 2.85, -0.25), (0.42, 0.2, 0.3), LIGHT_GREY)
        cyl(prims, (0, 2.85, -0.55), (0, 2.85, -0.62), 0.15, BLACK, n=16)
        cyl(prims, (0, 2.85, -0.62), (0, 2.85, -0.645), 0.09, (60, 110, 190), n=16, spec=0.9)
        box(prims, (0.3, 2.9, -0.551), (0.04, 0.04, 0.005), (60, 220, 90), spec=0.1)       # LED

        # boshqaruv shkafi va signal minorasi
        box(prims, (-5.2, 0.9, 0.2), (0.6, 0.9, 0.4), (96, 104, 114))
        box(prims, (-5.2, 1.1, 0.605), (0.5, 0.7, 0.005), (122, 130, 140), spec=0.3)
        box(prims, (-5.0, 1.45, 0.612), (0.22, 0.14, 0.006), (20, 40, 60), spec=0.8)       # displey
        cyl(prims, (-5.2, 1.8, 0.2), (-5.2, 2.4, 0.2), 0.05, STEEL, n=8)
        for k, col in enumerate(((60, 200, 90), (240, 190, 0), (222, 48, 44))):
            cyl(prims, (-5.2, 2.4 + 0.15 * k, 0.2), (-5.2, 2.55 + 0.15 * k, 0.2), 0.11, col, n=12)
        return prims

    # --- dinamik geometriya (har kadrda) ---
    def build(self):
        prims = []
        # konveyer chiziqlari (harakatni ko'rsatadi)
        for x, z0, z1, dr in ((0.0, -10.0, -2.0, +1), (-OUT_X, -9.0, -0.6, -1), (OUT_X, -9.0, -0.6, -1)):
            ln, hw = z1 - z0, BELT_W / 2
            for k in range(int(ln / 0.8) + 1):
                z = z0 + (k * 0.8 + dr * self.belt_off) % ln
                a, b = max(z0, z - 0.07), min(z1, z + 0.07)
                poly(prims, 1, [(x - hw, BELT_TOP + 0.002, a), (x + hw, BELT_TOP + 0.002, a),
                                (x + hw, BELT_TOP + 0.002, b), (x - hw, BELT_TOP + 0.002, b)],
                     (84, 92, 102), (0, 1, 0), False, 0.0)

        for arm in self.arms.values():
            arm.build(prims)

        # mahsulotlar: karton qutilar, ustida oq yorliq va lenta
        for it in self.items:
            c = tuple(it.pos)
            box(prims, c, (ITEM_H,) * 3, COLORS[it.color], spec=0.1)
            top = c[1] + ITEM_H + 0.004
            poly(prims, 2, [(c[0] - 0.12, top, c[2] - 0.12), (c[0] + 0.12, top, c[2] - 0.12),
                            (c[0] + 0.12, top, c[2] + 0.04), (c[0] - 0.12, top, c[2] + 0.04)],
                 (240, 240, 236), (0, 1, 0), False, 0.0, 0.15)
            poly(prims, 2, [(c[0] - 0.02, top, c[2] - ITEM_H), (c[0] + 0.02, top, c[2] - ITEM_H),
                            (c[0] + 0.02, top, c[2] + ITEM_H), (c[0] - 0.02, top, c[2] + ITEM_H)],
                 (225, 200, 150), (0, 1, 0), False, 0.0, 0.1)
        return prims


# --- ko'rinish (kamera + chizish) ----------------------------------------

def clip_near(cam):
    out = []
    n = len(cam)
    for i in range(n):
        a, b = cam[i], cam[(i + 1) % n]
        ina, inb = a[2] >= NEAR, b[2] >= NEAR
        if ina:
            out.append(a)
        if ina != inb:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR))
    return out


def rgb(c, k=1.0, add_=0.0):
    return tuple(max(0, min(255, int(v * k + add_))) for v in c)


def hexcol(c):
    return "#%02x%02x%02x" % tuple(c)


class Viewer:
    def __init__(self, root):
        self.root = root
        root.title("3D robot - rang bo'yicha saralash")
        self.cv = tk.Canvas(root, width=W, height=H, bg="#aeb9c2", highlightthickness=0)
        self.cv.pack()
        self.world = World()
        self.paused = False
        self.photo = None
        self.bg = self.make_background() if HAVE_PIL else None
        self.reset_camera()
        self.last_t = time.time()
        self.acc = 0.0

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<MouseWheel>", lambda e: self.zoom(0.9 if e.delta > 0 else 1.1))
        self.cv.bind("<Button-4>", lambda e: self.zoom(0.9))
        self.cv.bind("<Button-5>", lambda e: self.zoom(1.1))
        root.bind("<space>", lambda e: setattr(self, "paused", not self.paused))
        root.bind("<r>", lambda e: self.reset_camera())
        self.tick()

    @staticmethod
    def make_background():
        img = Image.new("RGB", (W * SS, H * SS))
        d = ImageDraw.Draw(img)
        for y in range(H * SS):
            k = y / (H * SS)
            d.line([(0, y), (W * SS, y)], fill=(int(120 + 70 * k), int(138 + 60 * k), int(155 + 50 * k)))
        return img

    def reset_camera(self):
        self.yaw, self.pitch, self.dist = 0.5, 0.5, 17.5
        self.target = (0.0, 1.5, -4.0)

    def on_press(self, e):
        self.last = (e.x, e.y)

    def on_drag(self, e):
        self.yaw -= (e.x - self.last[0]) * 0.008
        self.pitch = max(0.06, min(1.45, self.pitch + (e.y - self.last[1]) * 0.008))
        self.last = (e.x, e.y)

    def zoom(self, k):
        self.dist = max(5.0, min(45.0, self.dist * k))

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

    def scr(self, c, k=1):
        return (W / 2 + FOCAL * c[0] / c[2]) * k, (H / 2 - FOCAL * c[1] / c[2]) * k

    def compose(self):
        """Sahnani kameraga proyeksiyalab, uzoqdan yaqinga tartiblangan ro'yxat qaytaradi."""
        self.setup_camera()
        cpos = self.cpos
        draw = []
        for pr in self.world.static + self.world.build():
            kind = pr[0]
            if kind == "poly":
                _, layer, pts, col, n, edge, spec, bias = pr
                p0 = pts[0]
                v = (cpos[0] - p0[0], cpos[1] - p0[1], cpos[2] - p0[2])
                if dot(n, v) <= 0:                      # orqa yuz - ko'rinmaydi
                    continue
                m = pts[len(pts) // 2]
                cen = ((p0[0] + m[0]) / 2, (p0[1] + m[1]) / 2, (p0[2] + m[2]) / 2)
                cam = [self.to_cam(p) for p in pts]
                if min(c[2] for c in cam) < NEAR:
                    cam = clip_near(cam)
                    if len(cam) < 3:
                        continue
                cv = sub(cpos, cen)
                dist = length(cv)
                kd = max(0.0, dot(n, KEY_LIGHT))
                kf = max(0.0, dot(n, FILL_LIGHT))
                k = 0.34 + 0.62 * kd + 0.2 * kf
                sp = 0.0
                if spec > 0 and kd > 0:
                    hv = norm(add(KEY_LIGHT, mul(cv, 1 / dist)))
                    sp = max(0.0, dot(n, hv)) ** 28 * spec * 255
                shaded = rgb(col, k, sp)
                draw.append((layer, -(dist - bias), "poly", [self.scr(c) for c in cam], shaded,
                             rgb(shaded, 0.6) if edge else shaded))
            elif kind == "ball":
                _, layer, c, r, col = pr
                cc = self.to_cam(c)
                if cc[2] < NEAR:
                    continue
                x, y = self.scr(cc)
                draw.append((layer, -length(sub(c, cpos)), "ball", (x, y, r * FOCAL / cc[2]), col, None))
            else:
                _, layer, p0, p1, col = pr
                a, b = self.to_cam(p0), self.to_cam(p1)
                if a[2] < NEAR or b[2] < NEAR:
                    continue
                draw.append((layer, -length(sub(p0, cpos)), "line", self.scr(a) + self.scr(b), col, None))
        draw.sort(key=lambda t: (t[0], t[1]))
        return draw

    def paint_pil(self, draw):
        img = self.bg.copy()
        d = ImageDraw.Draw(img)
        for _, _, kind, g, col, edge in draw:
            if kind == "poly":
                d.polygon([(x * SS, y * SS) for x, y in g], fill=col, outline=edge)
            elif kind == "ball":
                x, y, r = g[0] * SS, g[1] * SS, g[2] * SS
                d.ellipse((x - r, y - r, x + r, y + r), fill=col, outline=rgb(col, 0.6))
            else:
                d.line([(g[0] * SS, g[1] * SS), (g[2] * SS, g[3] * SS)], fill=col, width=SS)
        return img.reduce(SS)

    def paint_canvas(self, draw):
        cv = self.cv
        for _, _, kind, g, col, edge in draw:
            if kind == "poly":
                cv.create_polygon(g, fill=hexcol(col), outline=hexcol(edge))
            elif kind == "ball":
                x, y, r = g
                cv.create_oval(x - r, y - r, x + r, y + r, fill=hexcol(col), outline=hexcol(rgb(col, 0.6)))
            else:
                cv.create_line(*g, fill=hexcol(col))

    def render(self):
        cv = self.cv
        cv.delete("all")
        draw = self.compose()
        if HAVE_PIL:
            self.photo = ImageTk.PhotoImage(self.paint_pil(draw))
            cv.create_image(0, 0, anchor="nw", image=self.photo)
        else:
            self.paint_canvas(draw)

        for text, p, col in (("KIRISH", (0, 2.3, -10.0), "#222"),
                             ("QIZIL", (-OUT_X, 2.3, -0.6), hexcol(COLORS["red"])),
                             ("KO'K", (OUT_X, 2.3, -0.6), hexcol(COLORS["blue"]))):
            c = self.to_cam(p)
            if c[2] > NEAR:
                x, y = self.scr(c)
                cv.create_text(x + 1, y + 1, text=text, fill="white", font=("Arial", 13, "bold"))
                cv.create_text(x, y, text=text, fill=col, font=("Arial", 13, "bold"))
        s = self.world.sorted
        cv.create_text(W / 2, 24, font=("Arial", 15, "bold"), fill="#12202b",
                       text=f"Saralandi  -  Qizil: {s['red']}    Ko'k: {s['blue']}")
        cv.create_text(W / 2, H - 14, font=("Arial", 10), fill="#12202b",
                       text="Sichqoncha: aylantirish  |  G'ildirak: zoom  |  SPACE: pauza  |  R: kamerani tiklash"
                            + ("" if HAVE_PIL else "  |  (pip install pillow - tiniqroq grafika uchun)"))

    def tick(self):
        now = time.time()
        self.acc += min(now - self.last_t, 0.2) * SIM_HZ
        self.last_t = now
        steps = int(self.acc)
        self.acc -= steps
        if not self.paused:
            for _ in range(min(steps, 6)):
                self.world.update()
        self.render()
        self.root.after(5, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    Viewer(root)
    root.mainloop()
