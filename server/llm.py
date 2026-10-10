"""Calls to the local open-weight model (Ollama) and the check-and-repair loops."""
from __future__ import annotations

import json
import os
import re
import time

import httpx

from . import plan as P

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("NAQSHA_MODEL", "qwen2.5vl:7b")
MAX_REPAIR_ROUNDS = int(os.environ.get("NAQSHA_REPAIR_ROUNDS", "2"))

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "rooms": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"},
            "w": {"type": "number"}, "h": {"type": "number"}},
            "required": ["name", "x", "y", "w", "h"]}},
        "doors": {"type": "array", "items": {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a", "b"]}},
    },
    "required": ["rooms", "doors"],
}

ROWS_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {"type": "array", "items": {"type": "object", "properties": {
            "rooms": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "w": {"type": "number"}, "h": {"type": "number"}},
                "required": ["name", "w", "h"]}}}, "required": ["rooms"]}},
        "doors": PLAN_SCHEMA["properties"]["doors"],
    },
    "required": ["rows", "doors"],
}

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "ops": {"type": "array", "items": {"type": "object", "properties": {
            "op": {"type": "string", "enum": ["resize", "set_size", "add_room", "remove_room",
                                              "rename", "swap", "add_door", "remove_door"]},
            "room": {"type": "string"}, "side": {"type": "string"}, "by": {"type": "number"},
            "w": {"type": "number"}, "h": {"type": "number"}, "name": {"type": "string"},
            "next_to": {"type": "string"}, "to": {"type": "string"},
            "a": {"type": "string"}, "b": {"type": "string"}}, "required": ["op"]}},
    },
    "required": ["reply", "ops"],
}

READ_PROMPT = """You are reading a hand-drawn floor plan of a single-storey house.
Return the plan as JSON. Units are FEET.

Coordinates: (0,0) is the top-left corner of the house. x grows to the RIGHT, y grows DOWN.
Each room is an axis-aligned rectangle: x, y = its top-left corner, w = width (left-right), h = height (top-bottom).

Rules:
1. Use the dimensions written on the sketch (e.g. "12x14" means w=12, h=14). If no size is written, estimate from the drawing.
2. Rooms that touch in the drawing must touch EXACTLY: the right edge (x+w) of one equals the left edge (x) of its neighbour; same for top/bottom.
3. Rooms must never overlap.
4. Use the label written in each room as its name (Bedroom, Kitchen, Lounge, Drawing Room, Bath, Car Porch, Lawn, Store ...). Make names unique: "Bedroom 1", "Bedroom 2".
5. doors: one entry per door drawn (a gap or arc in a wall). a and b are the two room names. Use b = "outside" for a door to the outside.
Return only JSON."""

READ_ROWS_PROMPT = """You are reading a hand-drawn floor plan of a single-storey house.
Read it as horizontal ROWS (bands of rooms), from the TOP of the drawing to the BOTTOM.
In each row, list the rooms from LEFT to RIGHT.

For each room give:
- name: the label written in the room (Bedroom, Kitchen, Lounge, Drawing Room, Bath, Car Porch, Lawn, Store ...). Make names unique: "Bedroom 1", "Bedroom 2".
- w, h: the size written in the room in FEET, e.g. "12x14" means w=12, h=14. If no size is written, estimate it.

doors: one entry per door drawn (a gap or arc in a wall) between two rooms that touch. a and b are room names; use b = "outside" for a door to the outside.
Return only JSON."""

EDIT_PROMPT = """You edit a house floor plan by emitting operations. Units are feet.
The user writes in English (e.g. "make the kitchen 2 ft bigger"). If they slip into Roman Urdu, understand it:
"bara" = bigger, "chhota" = smaller, "ke saath" / "ke paas" = next to, "washroom" = bath, "naya" = new, "hata do" = remove, "jagah badal do" = swap.

Directions: north = top/front, south = bottom/back, east = right, west = left.

Available ops (JSON objects):
- {"op":"resize","room":R,"side":"north|south|east|west","by":FEET}   (by > 0 grows, by < 0 shrinks; if no side is said, use east)
- {"op":"set_size","room":R,"w":FEET,"h":FEET}
- {"op":"add_room","name":NEW_NAME,"w":FEET,"h":FEET,"next_to":R,"side":"north|south|east|west"}   (a door to next_to is added automatically)
- {"op":"remove_room","room":R}
- {"op":"rename","room":R,"to":NEW_NAME}
- {"op":"swap","a":R1,"b":R2}   (the two rooms trade places)
- {"op":"add_door","a":R1,"b":R2 or "outside"}
- {"op":"remove_door","a":R1,"b":R2 or "outside"}

Use room names exactly as listed. If the user does not give a size for a new room, use a sensible one
(bath 7x8, bedroom 12x14, store 6x8, kitchen 10x12).
"reply" is one short friendly sentence confirming the change, always in English.
Return only JSON: {"reply": ..., "ops": [...]}"""


class ModelError(RuntimeError):
    pass


def _chat(messages, schema, timeout=180):
    # think=False: thinking models (e.g. Gemma 4) are much slower with no gain on this task
    body = {"model": MODEL, "messages": messages, "format": schema, "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 8192}, "keep_alive": "30m"}
    t0 = time.time()
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ModelError(f"could not reach Ollama at {OLLAMA_URL} ({e}). Is `ollama serve` running and `{MODEL}` pulled?")
    content = r.json()["message"]["content"]
    try:
        return json.loads(content), round(time.time() - t0, 1)
    except json.JSONDecodeError:
        raise ModelError(f"model returned invalid JSON: {content[:200]}")


def describe(plan):
    """Compact, model-friendly description of the current plan, including neighbours."""
    lines = []
    for r in plan["rooms"]:
        nb = []
        for o in plan["rooms"]:
            if o is r:
                continue
            sw = P.shared_wall(r, o)
            if sw:
                axis, c = sw[0], sw[1]
                if axis == "v":
                    side = "east" if abs(c - (r["x"] + r["w"])) < P.EPS else "west"
                else:
                    side = "south" if abs(c - (r["y"] + r["h"])) < P.EPS else "north"
                nb.append(f"{o['name']} ({side})")
        lines.append(f"- {r['name']}: {r['w']:g}x{r['h']:g} ft at x={r['x']:g}, y={r['y']:g}; neighbours: {', '.join(nb) or 'none'}")
    doors = ", ".join(f"{d['a']}<->{d['b']}" for d in plan["doors"])
    return "Rooms:\n" + "\n".join(lines) + f"\nDoors: {doors}"


def read_sketch(image_b64, rounds=MAX_REPAIR_ROUNDS, mode="rows"):
    """Image -> validated plan. Returns (plan, log, remaining_errors).
    mode="rows": the model only reads names + written sizes row by row and Naqsha's
    layout solver places the rooms (default). mode="coords": the model must output
    coordinates itself (naive baseline, kept for the benchmark)."""
    log = []
    prompt, schema = (READ_ROWS_PROMPT, ROWS_SCHEMA) if mode == "rows" else (READ_PROMPT, PLAN_SCHEMA)
    messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
    raw, secs = _chat(messages, schema)
    plan, errs = _check(raw, log, "model read the sketch", secs, mode)
    r = 0
    while errs and r < rounds:
        r += 1
        feedback = ("Your reading has these problems:\n" + "\n".join(f"- {e['msg']}" for e in errs)
                    + "\nLook at the drawing again, fix them and return the complete corrected JSON.")
        messages += [{"role": "assistant", "content": json.dumps(raw)}, {"role": "user", "content": feedback}]
        raw, secs = _chat(messages, schema)
        candidate, errs2 = _check(raw, log, f"repair round {r}: model re-read with checker feedback", secs, mode)
        if candidate is not None and (plan is None or len(errs2) <= len(errs)):
            plan, errs = candidate, errs2
    if plan is None:
        raise ModelError("the model could not produce a usable plan from this image")
    return plan, log, errs


def _check(raw, log, stage, secs, mode):
    try:
        if mode == "rows":
            plan, layout_fixes = P.layout_rows(raw)
        else:
            plan, layout_fixes = P.normalise(raw), []
    except P.PlanError as e:
        log.append({"stage": stage, "secs": secs, "raw_errors": 1, "fixes": [], "errors": [{"code": "schema", "msg": str(e)}]})
        return None, [{"code": "schema", "msg": str(e)}]
    raw_errs = P.validate(plan)
    plan, fixes = P.repair(plan)
    errs = P.validate(plan)
    log.append({"stage": stage, "secs": secs, "rooms": len(plan["rooms"]),
                "raw_errors": len(raw_errs) + len(layout_fixes), "fixes": layout_fixes + fixes, "errors": errs})
    return plan, errs


DESIGN_PROMPT = """You are an architect designing a single-storey Pakistani house. Units are FEET.
Describe the house as horizontal ROWS (bands of rooms) from the FRONT (street, top) to the BACK (bottom).
In each row list the rooms from LEFT to RIGHT with name, w (width, left-right) and h (depth, top-bottom).

Rules:
1. Row 1 (at the street) must contain the "Car Porch" and the "Drawing Room".
2. Next row(s): "Lounge", "Kitchen", "Dining" (if asked).
3. Then the bedrooms, each with an attached bath next to it ("Bedroom 1", "Bath 1", "Bedroom 2", "Bath 2" ...).
4. If a lawn is requested, put "Lawn" alone as the LAST row, spanning the full width.
5. Every row must add up to the SAME total width (the plot width). Rooms in one row share the same h.
6. Follow any plot size given. 1 marla = 225 sq ft. 5 marla ~ 25x45 ft, 7 marla ~ 30x52 ft,
   10 marla ~ 35x65 ft, 1 kanal ~ 50x90 ft (width x depth). The rows' depths should add up to about the plot depth.
7. Unique names ("Bedroom 1", "Bedroom 2", "Bath 1" ...). Realistic sizes: bedroom 12-16 ft, bath 6-8 ft wide,
   kitchen 10-12 ft, lounge 14-20 ft, drawing room 12-16 ft, car porch 10-14 ft wide.
8. doors: connect rooms that touch: Car Porch <-> "outside", Car Porch <-> Drawing Room, Drawing Room <-> Lounge,
   Lounge <-> Kitchen, Lounge <-> each Bedroom, each Bedroom <-> its Bath, Lounge <-> Lawn.
Return only JSON."""


MIN_DEPTH = [(r"bed", 12), (r"lounge|tv|family", 13), (r"drawing|guest", 12), (r"porch|garage|car", 16),
             (r"kitchen", 10), (r"dining", 10), (r"lawn|garden", 10)]


def plot_width(prompt):
    """Plot width in ft implied by '10 marla' / '1 kanal' / '35x65' in the brief (default 35)."""
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|')?\s*(?:x|×|by)\s*(\d+(?:\.\d+)?)", prompt, re.I):
        return min(float(m.group(1)), float(m.group(2)))
    marla = None
    if m := re.search(r"(\d+(?:\.\d+)?)\s*kanal", prompt, re.I):
        marla = float(m.group(1)) * 20
    elif m := re.search(r"(\d+(?:\.\d+)?)\s*marla", prompt, re.I):
        marla = float(m.group(1))
    if not marla:
        return 35.0
    return float(round((marla * P.SQFT_PER_MARLA / 1.85) ** 0.5))  # plots are ~1:1.85 (10 marla ~ 35x65)


def _tidy_rows(raw, width):
    """Small models cram every bedroom into one very wide, shallow row. Split rows wider
    than the plot (keeping each bath with its bedroom), give rooms a sensible minimum
    depth, and fit every row to the plot width. Returns (raw, notes)."""
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return raw, []
    notes, out = [], []
    for row in rows:
        items = [r for r in ((row.get("rooms") if isinstance(row, dict) else row) or [])
                 if isinstance(r, dict) and r.get("name") and P._num(r.get("w")) and P._num(r.get("h"))]
        if not items:
            continue
        units = []
        for r in items:  # a bath rides along with the bedroom before it
            if units and re.search(r"bath|wash|toilet", r["name"], re.I) and re.search(r"bed", units[-1][-1]["name"], re.I):
                units[-1].append(r)
            else:
                units.append([r])
        packed, cur = [], []
        for u in units:
            if cur and sum(P._num(r["w"]) for r in cur + u) > width * 1.3:
                packed.append(cur)
                cur = []
            cur += u
        packed.append(cur)
        if len(packed) > 1:
            notes.append(f"split a {sum(P._num(r['w']) for r in items):g} ft wide row into {len(packed)} rows to fit the {width:g} ft plot")
        out += packed
    for row in out:
        hs = [P._num(r["h"]) for r in row]
        need = max([d for r in row for pat, d in MIN_DEPTH if re.search(pat, r["name"], re.I)] or [0])
        cap = 22 if any(re.search(r"porch|garage|car|lawn|garden", r["name"], re.I) for r in row) else 18
        h0 = max(set(hs), key=lambda v: (hs.count(v), v))
        h = min(max(h0, need), max(cap, need))
        if h != h0:
            notes.append(f"{', '.join(r['name'] for r in row)} row was {h0:g} ft deep: set to {h:g} ft")
        ws0 = [P._num(r["w"]) for r in row]
        bath = [bool(re.search(r"bath|wash|toilet", r["name"], re.I)) for r in row]
        if sum(ws0) < width and not all(bath) and any(bath):  # growing: baths keep their width
            fixed = sum(w for w, b in zip(ws0, bath) if b)
            k = (width - fixed) / (sum(ws0) - fixed)
            ws = [w if b else round(w * k * 2) / 2 for w, b in zip(ws0, bath)]
        else:
            k = width / sum(ws0)
            ws = [round(w * k * 2) / 2 for w in ws0]
        # absorb rounding in the last non-bath room so every row is exactly the plot width
        i = max((j for j, b in enumerate(bath) if not b), default=len(ws) - 1)
        ws[i] += width - sum(ws)
        for r, w in zip(row, ws):
            r["w"], r["h"] = w, h
    return {"rows": [{"rooms": row} for row in out], "doors": raw.get("doors") or []}, notes


def design_plan(prompt, rounds=1):
    """Text brief -> designed + validated plan. Returns (plan, log). Raises ModelError."""
    log = []
    width = plot_width(prompt)
    messages = [{"role": "system", "content": DESIGN_PROMPT},
                {"role": "user", "content": f"Design this house (plot width {width:g} ft, so the w values in every row add up to {width:g} ft; "
                                            f"h is each room's own depth, usually 10-18 ft; at most 2 bedrooms per row): {prompt}"}]
    raw, secs = _chat(messages, ROWS_SCHEMA)
    raw, tidy = _tidy_rows(raw, width)
    plan, errs = _check(raw, log, "model designed the house", secs, "rows")
    if tidy and log:
        log[-1]["fixes"] = tidy + log[-1]["fixes"]
    r = 0
    while errs and r < rounds:
        r += 1
        feedback = ("Your design has these problems:\n" + "\n".join(f"- {e['msg']}" for e in errs)
                    + "\nFix them and return the complete corrected JSON.")
        messages += [{"role": "assistant", "content": json.dumps(raw)}, {"role": "user", "content": feedback}]
        raw, secs = _chat(messages, ROWS_SCHEMA)
        raw, tidy = _tidy_rows(raw, width)
        candidate, errs2 = _check(raw, log, f"repair round {r}: model redesigned with checker feedback", secs, "rows")
        if tidy:
            log[-1]["fixes"] = tidy + log[-1]["fixes"]
        if candidate is not None and (plan is None or len(errs2) <= len(errs)):
            plan, errs = candidate, errs2
    if plan is None:
        raise ModelError("the model could not design a usable plan from this description")
    return plan, log


DIMS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:x|×|\*|by)\s*(\d+(?:\.\d+)?)", re.I)
SIDE_WORDS = re.compile(r"(?<![a-z])(east|west|north|south|left|right|front|back|top|bottom)(?![a-z])", re.I)


def _fill_gaps(ops, instruction):
    """Small models sometimes put a size or side in the wrong field. Recover them from
    the op's other string fields, then from the user's own words."""
    for op in ops:
        if op.get("op") not in ("add_room", "resize"):
            continue
        texts = [v for v in op.values() if isinstance(v, str)] + [instruction]
        said = DIMS.search(instruction) if sum(o.get("op") == "add_room" for o in ops) == 1 else None
        if op["op"] == "add_room" and said:  # the user's own words win over the model's guess
            op["w"], op["h"] = float(said.group(1)), float(said.group(2))
        elif op["op"] == "add_room" and (not op.get("w") or not op.get("h")):
            for t in texts:
                if m := DIMS.search(t):
                    op["w"], op["h"] = float(m.group(1)), float(m.group(2))
                    break
        if not op.get("side") or str(op.get("side")).lower() not in P.SIDE_ALIASES:
            for t in texts:
                if m := SIDE_WORDS.search(t):
                    op["side"] = m.group(1).lower()
                    break
    return ops


def edit_plan(plan, instruction, rounds=1):
    """Natural-language edit -> ops -> applied + validated plan. Returns (plan, reply, ops, log)."""
    log = []
    messages = [{"role": "system", "content": EDIT_PROMPT},
                {"role": "user", "content": describe(plan) + f"\n\nInstruction: {instruction}"}]
    for attempt in range(rounds + 1):
        out, secs = _chat(messages, EDIT_SCHEMA, timeout=120)
        ops = _fill_gaps(out.get("ops") or [], instruction)
        problem = None
        try:
            if not ops:
                raise P.PlanError("no operations were produced")
            new, notes = P.apply_ops(plan, ops)
            new, fixes = P.repair(new)
            errs = P.validate(new)
            if errs:
                problem = "; ".join(e["msg"] for e in errs)
        except (P.PlanError, TypeError, ValueError) as e:
            problem, notes, fixes = str(e), [], []
        log.append({"stage": "model proposed edit" if attempt == 0 else "retry after checker feedback",
                    "secs": secs, "ops": ops, "notes": notes, "fixes": fixes, "problem": problem})
        if not problem:
            return new, out.get("reply") or "Done.", ops, log
        messages += [{"role": "assistant", "content": json.dumps(out)},
                     {"role": "user", "content": f"That failed: {problem}. Return corrected ops."}]
    raise ModelError(f"could not apply that edit: {problem}")
