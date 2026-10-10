"""Render demo sketch photos for the upload button, one per common house size.
Output: samples/<name>.png + <name>.json (ground truth).   Run:  python -m samples.make_images"""
import json
import random
from pathlib import Path

from bench.make_sketches import render
from server import plan as P

OUT = Path(__file__).resolve().parent

# Each row spans the full house width: (row height, [(room, width), ...]), all in feet.
LAYOUTS = {
    "five_marla": [
        (12, [("Car Porch", 11), ("Drawing Room", 14)]),
        (14, [("Lounge", 15), ("Kitchen", 10)]),
        (12, [("Bedroom 1", 13), ("Bath 1", 7), ("Store", 5)]),
        (12, [("Bedroom 2", 18), ("Bath 2", 7)]),
    ],
    "seven_marla": [
        (14, [("Car Porch", 12), ("Drawing Room", 18)]),
        (14, [("Kitchen", 11), ("Lounge", 19)]),
        (13, [("Bedroom 1", 14), ("Bath 1", 7), ("Bedroom 2", 9)]),
        (10, [("Store", 6), ("Bath 2", 7), ("Lawn", 17)]),
    ],
    "one_kanal": [
        (16, [("Car Porch", 20), ("Drawing Room", 30)]),
        (16, [("Kitchen", 14), ("Dining", 14), ("Lounge", 22)]),
        (15, [("Bedroom 1", 16), ("Bath 1", 8), ("Bedroom 2", 16), ("Store", 10)]),
        (15, [("Bedroom 3", 16), ("Bath 2", 8), ("Lawn", 26)]),
    ],
}


def build(rows):
    rooms, y = [], 0
    for h, row in rows:
        x = 0
        for name, w in row:
            rooms.append({"name": name, "x": x, "y": y, "w": w, "h": h})
            x += w
        y += h
    plan, _ = P.repair({"rooms": rooms, "doors": [{"a": "Car Porch", "b": "outside"}]})
    return plan


def main(seed=11):
    rng = random.Random(seed)
    plans = {name: build(rows) for name, rows in LAYOUTS.items()}
    plans["ten_marla"] = json.loads((OUT / "ten_marla.json").read_text())
    for name, plan in plans.items():
        errs = P.validate(plan)
        assert not errs, (name, errs)
        render(plan, rng).save(OUT / f"{name}.png")
        if name != "ten_marla":
            (OUT / f"{name}.json").write_text(json.dumps(plan, indent=1))
        print(f"{name}: {len(plan['rooms'])} rooms -> {name}.png")


if __name__ == "__main__":
    main()
