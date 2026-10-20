"""Mobil robot - mahsulotlarni rangiga qarab saralash simulyatsiyasi.

Faqat standart kutubxona (tkinter) kerak. PyCharm'da shu faylni Run qiling.

Sxema (tepdan ko'rinish):
    [ KIRISH KONVEYERI  ->  -> -> [PICK] ]      (qizil va ko'k mahsulotlar)
                      ^ robot (harakatlanadi)
    [ QIZIL konveyer ]                [ KO'K konveyer ]
"""
import math
import random
import tkinter as tk

W, H = 900, 600
FPS = 60
ITEM = 30                      # mahsulot o'lchami
COLORS = {"red": "#e53935", "blue": "#1e88e5"}

# Konveyerlar (x1, y1, x2, y2)
IN_BELT = (40, 60, 620, 120)
PICK = (590, 90)               # kirish konveyeri oxiri (olish nuqtasi)
OUT_BELTS = {
    "red": (40, 480, 330, 540),    # chap pastda
    "blue": (570, 480, 860, 540),  # o'ng pastda
}
DROP = {c: ((b[0] + b[2]) / 2 - 60, (b[1] + b[3]) / 2) for c, b in OUT_BELTS.items()}

BELT_SPEED = 1.6
ROBOT_SPEED = 3.2


class Item:
    def __init__(self, color, x, y):
        self.color, self.x, self.y = color, x, y
        self.state = "in"      # in | carried | out


class Robot:
    def __init__(self):
        self.x, self.y = 450.0, 300.0
        self.item = None
        self.state = "idle"    # idle -> to_pick -> to_drop -> back
        self.target = None

    def move_to(self, tx, ty):
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d <= ROBOT_SPEED:
            self.x, self.y = tx, ty
            return True
        self.x += dx / d * ROBOT_SPEED
        self.y += dy / d * ROBOT_SPEED
        return False


class App:
    def __init__(self, root):
        self.root = root
        root.title("Robot - rang bo'yicha saralash")
        self.cv = tk.Canvas(root, width=W, height=H, bg="#eceff1")
        self.cv.pack()
        self.robot = Robot()
        self.items = []
        self.sorted = {"red": 0, "blue": 0}
        self.spawn_timer = 0
        self.tick()

    # --- mantiq ---
    def spawn(self):
        # kirish konveyeri boshida joy bo'sh bo'lsa yangi mahsulot qo'yamiz
        if any(i.state == "in" and i.x < IN_BELT[0] + ITEM * 2 for i in self.items):
            return
        color = random.choice(list(COLORS))
        self.items.append(Item(color, IN_BELT[0] + 20, (IN_BELT[1] + IN_BELT[3]) / 2))

    def update(self):
        self.spawn_timer += 1
        if self.spawn_timer > 70:
            self.spawn_timer = 0
            self.spawn()

        # kirish konveyeridagi mahsulotlar oxirigacha yuradi va to'xtaydi
        queue = sorted((i for i in self.items if i.state == "in"), key=lambda i: -i.x)
        limit = PICK[0]
        for it in queue:
            it.x = min(it.x + BELT_SPEED, limit)
            limit = it.x - ITEM - 4

        # chiqish konveyerlari mahsulotlarni olib ketadi
        for it in self.items:
            if it.state == "out":
                it.x += BELT_SPEED if it.color == "blue" else -BELT_SPEED

        r = self.robot
        if r.state == "idle":
            front = next((i for i in queue if abs(i.x - PICK[0]) < 1), None)
            if front:
                r.target, r.state = front, "to_pick"
        elif r.state == "to_pick":
            if r.move_to(PICK[0] - 10, PICK[1] + 55):
                r.item = r.target
                r.item.state = "carried"      # sensor rangni aniqladi, ushlab oldi
                r.state = "to_drop"
        elif r.state == "to_drop":
            tx, ty = DROP[r.item.color]
            if r.move_to(tx, ty - 50):
                r.item.state = "out"
                r.item.x, r.item.y = tx, ty
                self.sorted[r.item.color] += 1
                r.item, r.state = None, "back"
        elif r.state == "back":
            if r.move_to(450, 300):
                r.state = "idle"

        if r.item:
            r.item.x, r.item.y = r.x, r.y - 25

        # ekrandan chiqib ketganlarni o'chirish
        self.items = [i for i in self.items if -50 < i.x < W + 50]

    # --- chizish ---
    def belt(self, b, label, color=None):
        self.cv.create_rectangle(*b, fill="#455a64", outline="black", width=2)
        for x in range(int(b[0]), int(b[2]), 30):
            self.cv.create_line(x, b[1], x, b[3], fill="#607d8b")
        self.cv.create_text((b[0] + b[2]) / 2, b[1] - 14, text=label,
                            font=("Arial", 11, "bold"),
                            fill=COLORS[color] if color else "black")

    def draw(self):
        c = self.cv
        c.delete("all")
        self.belt(IN_BELT, "KIRISH KONVEYERI")
        self.belt(OUT_BELTS["red"], "QIZIL mahsulotlar", "red")
        self.belt(OUT_BELTS["blue"], "KO'K mahsulotlar", "blue")

        for it in self.items:
            h = ITEM / 2
            c.create_rectangle(it.x - h, it.y - h, it.x + h, it.y + h,
                               fill=COLORS[it.color], outline="black", width=2)

        r = self.robot
        # robot korpusi, g'ildiraklari, qo'li
        c.create_rectangle(r.x - 28, r.y - 18, r.x + 28, r.y + 22,
                           fill="#ffb300", outline="black", width=2)
        for wx in (-28, 22):
            for wy in (-18, 14):
                c.create_rectangle(r.x + wx - 3, r.y + wy, r.x + wx + 9, r.y + wy + 10,
                                   fill="black")
        c.create_oval(r.x - 6, r.y - 6, r.x + 6, r.y + 6, fill="#d32f2f")
        c.create_line(r.x, r.y - 18, r.x, r.y - 36, width=5, fill="#37474f")
        c.create_text(r.x, r.y + 38, text="ROBOT", font=("Arial", 9, "bold"))

        c.create_text(W / 2, 20, font=("Arial", 13, "bold"),
                      text=f"Saralandi  -  Qizil: {self.sorted['red']}   "
                           f"Ko'k: {self.sorted['blue']}")

    def tick(self):
        self.update()
        self.draw()
        self.root.after(1000 // FPS, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
