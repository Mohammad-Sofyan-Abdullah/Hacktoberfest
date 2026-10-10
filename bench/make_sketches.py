"""Generate synthetic hand-drawn-style floor plan sketches with known ground truth.
Output: bench/sketches/NN.png + NN.json.   Run:  python -m bench.make_sketches"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from server import plan as P

OUT = Path(__file__).resolve().parent / "sketches"
PX = 12  # pixels per foot
M = 60   # margin

ROWS = [
    [("Car Porch", 12), ("Drawing Room", 18)],
    [("Kitchen", 10), ("Lounge", 20)],
    [("Bedroom 1", 14), ("Bath 1", 7), ("Bedroom 2", 13)],
    [("Store", 6), ("Dining", 12), ("Bedroom 3", 14)],
    [("Lawn", 30)],
]


def make_plan(rng):
    """Rows of rooms stacked top to bottom; each row spans the same total width."""
    width = rng.choice([30, 32, 35, 40])
    rows = [ROWS[0], ROWS[1], ROWS[2]] + rng.sample(ROWS[3:], rng.randint(0, 2))
    rooms, y = [], 0
    for row in rows:
        h = rng.choice([10, 12, 14, 16])
        total = sum(w for _, w in row)
        x = 0
        for i, (name, w) in enumerate(row):
            ww = width - x if i == len(row) - 1 else max(5, round(w * width / total))
            rooms.append({"name": name, "x": x, "y": y, "w": ww, "h": h})
            x += ww
        y += h
    plan = {"rooms": rooms, "doors": [{"a": rooms[0]["name"], "b": "outside"}]}
    plan, _ = P.repair(plan)  # auto-doors give a realistic connected layout
    return plan


def wobbly(draw, p1, p2, rng, width=3):
    n = max(2, int(abs(p2[0] - p1[0]) + abs(p2[1] - p1[1])) // 25)
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append((p1[0] + (p2[0] - p1[0]) * t + rng.uniform(-1.5, 1.5),
                    p1[1] + (p2[1] - p1[1]) * t + rng.uniform(-1.5, 1.5)))
    draw.line(pts, fill=(30, 30, 40), width=width, joint="curve")


def font(size):
    for name in ("segoepr.ttf", "comic.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def render(plan, rng):
    s = P.stats(plan)
    img = Image.new("RGB", (int(s["footprint_w"] * PX + 2 * M), int(s["footprint_h"] * PX + 2 * M)), (250, 248, 240))
    d = ImageDraw.Draw(img)
    g = P.geometry(plan)
    for w in g["walls"]:
        if w["axis"] == "h":
            wobbly(d, (M + w["lo"] * PX, M + w["c"] * PX), (M + w["hi"] * PX, M + w["c"] * PX), rng)
        else:
            wobbly(d, (M + w["c"] * PX, M + w["lo"] * PX), (M + w["c"] * PX, M + w["hi"] * PX), rng)
    for door in g["doors"]:  # little arc in each door gap
        r = (door["hi"] - door["lo"]) * PX
        if door["axis"] == "h":
            cx, cy = M + door["lo"] * PX, M + door["c"] * PX
        else:
            cx, cy = M + door["c"] * PX, M + door["lo"] * PX
        d.arc([cx - r, cy - r, cx + r, cy + r], 0, 90, fill=(120, 120, 140), width=2)
    f1, f2 = font(22), font(18)
    for room in plan["rooms"]:
        cx, cy = M + (room["x"] + room["w"] / 2) * PX, M + (room["y"] + room["h"] / 2) * PX
        d.text((cx, cy - 12), room["name"], fill=(20, 20, 60), font=f1, anchor="mm")
        d.text((cx, cy + 14), f"{room['w']:g}x{room['h']:g}", fill=(60, 60, 90), font=f2, anchor="mm")
    return img.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor=(250, 248, 240))


def main(n=8, seed=7):
    OUT.mkdir(exist_ok=True)
    rng = random.Random(seed)
    for i in range(n):
        plan = make_plan(rng)
        render(plan, rng).save(OUT / f"{i:02d}.png")
        (OUT / f"{i:02d}.json").write_text(json.dumps(plan, indent=1))
    print(f"wrote {n} sketches to {OUT}")


if __name__ == "__main__":
    main()
