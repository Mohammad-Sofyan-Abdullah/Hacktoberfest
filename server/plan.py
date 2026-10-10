"""Naqsha plan engine: schema checks, deterministic repair, edit operations and
2D -> wall geometry. Pure Python, no model calls, so every rule here is testable.

A plan is plain JSON, all units in feet, origin at the top-left of the house,
x grows east (right) and y grows south (down):

    {"rooms": [{"name": "Kitchen", "x": 0, "y": 20, "w": 12, "h": 12}, ...],
     "doors": [{"a": "Kitchen", "b": "Lounge"}, {"a": "Car Porch", "b": "outside"}]}
"""
from __future__ import annotations

import copy
import difflib
import re

EPS = 0.01
SNAP_TOL = 1.0          # edges closer than this (ft) are treated as the same wall
MIN_DOOR_WALL = 2.5     # a door needs at least this much shared wall (ft)
DOOR_WIDTH = 3.0
MIN_ROOM = 2.0
SQFT_PER_MARLA = 225.0  # CDA/LDA convention; configurable in the UI
OUTSIDE = "outside"


class PlanError(ValueError):
    pass


# ---------------------------------------------------------------- helpers

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _box(r):
    return r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]


def _overlap_1d(a1, a2, b1, b2):
    return max(0.0, min(a2, b2) - max(a1, b1))


def shared_wall(a, b):
    """Return (axis, coord, lo, hi) of the wall a and b share, or None.
    axis 'v' = vertical line x=coord, 'h' = horizontal line y=coord."""
    ax1, ay1, ax2, ay2 = _box(a)
    bx1, by1, bx2, by2 = _box(b)
    for ac, bc in ((ax2, bx1), (ax1, bx2)):
        if abs(ac - bc) < EPS:
            ov = _overlap_1d(ay1, ay2, by1, by2)
            if ov > EPS:
                return "v", ac, max(ay1, by1), min(ay2, by2)
    for ac, bc in ((ay2, by1), (ay1, by2)):
        if abs(ac - bc) < EPS:
            ov = _overlap_1d(ax1, ax2, bx1, bx2)
            if ov > EPS:
                return "h", ac, max(ax1, bx1), min(ax2, bx2)
    return None


def _subtract(intervals, cut_lo, cut_hi):
    out = []
    for lo, hi in intervals:
        if cut_hi <= lo + EPS or cut_lo >= hi - EPS:
            out.append((lo, hi))
            continue
        if cut_lo > lo + EPS:
            out.append((lo, cut_lo))
        if cut_hi < hi - EPS:
            out.append((cut_hi, hi))
    return out


def _edges(r):
    x1, y1, x2, y2 = _box(r)
    return [("h", y1, x1, x2), ("h", y2, x1, x2), ("v", x1, y1, y2), ("v", x2, y1, y2)]


def exterior_wall(room, rooms):
    """Longest stretch of this room's boundary not shared with another room."""
    best = None
    for axis, c, lo, hi in _edges(room):
        free = [(lo, hi)]
        for o in rooms:
            if o is room:
                continue
            for oa, oc, olo, ohi in _edges(o):
                if oa == axis and abs(oc - c) < EPS:
                    free = _subtract(free, olo, ohi)
        for flo, fhi in free:
            if best is None or fhi - flo > best[3] - best[2]:
                best = (axis, c, flo, fhi)
    return best


def find_room(plan, name):
    """Forgiving room lookup: exact, case-insensitive, prefix, substring, fuzzy."""
    if not name:
        raise PlanError("missing room name")
    rooms = plan["rooms"]
    key = str(name).strip().lower()
    for test in (lambda n: n == key, lambda n: n.startswith(key),
                 lambda n: key in n, lambda n: n in key):
        hits = [r for r in rooms if test(r["name"].lower())]
        if len(hits) == 1:
            return hits[0]
    close = difflib.get_close_matches(key, [r["name"].lower() for r in rooms], n=1, cutoff=0.6)
    if close:
        return next(r for r in rooms if r["name"].lower() == close[0])
    raise PlanError(f"no room called '{name}'. Rooms are: " + ", ".join(r["name"] for r in rooms))


# ---------------------------------------------------------------- normalise + check

def normalise(raw):
    """Coerce model output into the schema. Raises PlanError on unusable input."""
    if not isinstance(raw, dict) or not isinstance(raw.get("rooms"), list) or not raw["rooms"]:
        raise PlanError("plan must contain a non-empty 'rooms' list")
    rooms = []
    for i, r in enumerate(raw["rooms"]):
        if not isinstance(r, dict):
            raise PlanError(f"room #{i + 1} is not an object")
        vals = {k: _num(r.get(k)) for k in ("x", "y", "w", "h")}
        if any(v is None for v in vals.values()):
            raise PlanError(f"room #{i + 1} ({r.get('name')}) needs numeric x, y, w, h")
        name = str(r.get("name") or f"Room {i + 1}").strip()
        rooms.append({"name": name, **vals})
    doors = []
    for d in raw.get("doors") or []:
        if isinstance(d, dict) and d.get("a") and d.get("b"):
            doors.append({"a": str(d["a"]).strip(), "b": str(d["b"]).strip()})
    plan = {"rooms": rooms, "doors": doors}
    _translate_to_origin(plan)
    return plan


def _translate_to_origin(plan):
    mx = min(r["x"] for r in plan["rooms"])
    my = min(r["y"] for r in plan["rooms"])
    for r in plan["rooms"]:
        r["x"] = round(r["x"] - mx, 2)
        r["y"] = round(r["y"] - my, 2)


def _door_rooms(plan, d):
    names = {r["name"].lower(): r for r in plan["rooms"]}
    a = names.get(d["a"].lower())
    b = None if d["b"].lower() == OUTSIDE else names.get(d["b"].lower())
    return a, b


def validate(plan):
    """Return a list of {code, msg} problems. Empty list = buildable plan."""
    errs = []
    rooms = plan["rooms"]
    seen = set()
    for r in rooms:
        if r["w"] < MIN_ROOM or r["h"] < MIN_ROOM:
            errs.append({"code": "too_small", "msg": f"{r['name']} is {r['w']}x{r['h']} ft; rooms must be at least {MIN_ROOM} ft on each side"})
        if r["w"] > 300 or r["h"] > 300:
            errs.append({"code": "too_big", "msg": f"{r['name']} is {r['w']}x{r['h']} ft, which is not plausible"})
        if r["name"].lower() in seen:
            errs.append({"code": "dup_name", "msg": f"two rooms are called '{r['name']}'; names must be unique (e.g. 'Bedroom 1', 'Bedroom 2')"})
        seen.add(r["name"].lower())
    for i, a in enumerate(rooms):
        ax1, ay1, ax2, ay2 = _box(a)
        for b in rooms[i + 1:]:
            bx1, by1, bx2, by2 = _box(b)
            area = _overlap_1d(ax1, ax2, bx1, bx2) * _overlap_1d(ay1, ay2, by1, by2)
            if area > 1.0:
                errs.append({"code": "overlap", "msg": f"{a['name']} and {b['name']} overlap by {area:.0f} sq ft; rooms must touch, not overlap"})
    for d in plan["doors"]:
        a, b = _door_rooms(plan, d)
        if a is None or (b is None and d["b"].lower() != OUTSIDE):
            errs.append({"code": "door_unknown", "msg": f"door {d['a']} -> {d['b']} names a room that does not exist"})
            continue
        if b is None:
            ext = exterior_wall(a, rooms)
            if ext is None or ext[3] - ext[2] < MIN_DOOR_WALL:
                errs.append({"code": "door_no_exterior", "msg": f"{a['name']} has no outside wall for its door to outside"})
        else:
            sw = shared_wall(a, b)
            if sw is None or sw[3] - sw[2] < MIN_DOOR_WALL:
                errs.append({"code": "door_not_adjacent", "msg": f"door between {a['name']} and {b['name']}, but they do not share a wall"})
    return errs


def unreachable(plan):
    """Rooms you cannot walk to from outside through doors."""
    adj = {r["name"].lower(): set() for r in plan["rooms"]}
    adj[OUTSIDE] = set()
    for d in plan["doors"]:
        a, b = d["a"].lower(), d["b"].lower()
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen, stack = {OUTSIDE}, [OUTSIDE]
    while stack:
        for n in adj[stack.pop()]:
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return [r for r in plan["rooms"] if r["name"].lower() not in seen]


# ---------------------------------------------------------------- layout solver

def layout_rows(raw):
    """Place rooms from a row-by-row reading (what small vision models are good at:
    names + written sizes, top-to-bottom, left-to-right) instead of trusting
    model-generated coordinates. Reconciles inconsistent sizes. Returns (plan, fixes)."""
    rows = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise PlanError("expected a non-empty 'rows' list")
    clean = []
    for i, row in enumerate(rows):
        items = row.get("rooms") if isinstance(row, dict) else row
        rr = []
        for r in items or []:
            w, h = _num(r.get("w")), _num(r.get("h"))
            if not r.get("name") or not w or not h or w <= 0 or h <= 0:
                raise PlanError(f"row {i + 1}: every room needs a name and positive w, h (got {r})")
            rr.append({"name": str(r["name"]).strip(), "w": w, "h": h})
        if rr:
            clean.append(rr)
    if not clean:
        raise PlanError("no rooms found in rows")

    fixes = []
    sums = [round(sum(r["w"] for r in row) * 2) / 2 for row in clean]
    common = max(set(sums), key=lambda s: (sums.count(s), s))
    width = common if sums.count(common) > 1 else max(sums)
    rooms, y = [], 0.0
    for i, row in enumerate(clean):
        gap = width - sum(r["w"] for r in row)
        if abs(gap) > EPS:
            last = row[-1]
            if last["w"] + gap >= MIN_ROOM and abs(gap) <= 0.4 * last["w"] + 1:
                fixes.append(f"row {i + 1} was {width - gap:g} ft wide, house is {width:g} ft: {'widened' if gap > 0 else 'narrowed'} {last['name']} by {abs(gap):g} ft")
                last["w"] += gap
            else:
                k = width / (width - gap)
                for r in row:
                    r["w"] = round(r["w"] * k * 2) / 2
                row[-1]["w"] = width - sum(r["w"] for r in row[:-1])
                fixes.append(f"row {i + 1} was {width - gap:g} ft wide, house is {width:g} ft: scaled its rooms to fit")
        hs = [r["h"] for r in row]
        height = max(set(hs), key=lambda v: (hs.count(v), v))
        x = 0.0
        for r in row:
            if abs(r["h"] - height) > EPS:
                fixes.append(f"{r['name']} was {r['h']:g} ft deep, its row is {height:g} ft: matched to the row")
            rooms.append({"name": r["name"], "x": x, "y": y, "w": r["w"], "h": height})
            x += r["w"]
        y += height
    plan = normalise({"rooms": rooms, "doors": raw.get("doors") or []})
    return plan, fixes


# ---------------------------------------------------------------- deterministic repair

def _snap_axis(rooms, lo_key, len_key):
    vals = sorted({v for r in rooms for v in (r[lo_key], r[lo_key] + r[len_key])})
    clusters, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[0] <= SNAP_TOL:
            cur.append(v)
        else:
            clusters.append(cur)
            cur = [v]
    clusters.append(cur)
    mapping = {}
    for c in clusters:
        target = round(sum(c) / len(c) * 2) / 2  # nearest half foot
        for v in c:
            mapping[v] = target
    moved = sum(1 for v, t in mapping.items() if abs(v - t) > EPS)
    for r in rooms:
        lo, hi = mapping[r[lo_key]], mapping[r[lo_key] + r[len_key]]
        r[lo_key], r[len_key] = lo, hi - lo
    return moved


def repair(plan):
    """Fix what can be fixed without the model. Returns (plan, list of fixes)."""
    plan = copy.deepcopy(plan)
    fixes = []
    moved = _snap_axis(plan["rooms"], "x", "w") + _snap_axis(plan["rooms"], "y", "h")
    if moved:
        fixes.append(f"snapped {moved} near-miss wall edges so rooms share walls exactly")
    _translate_to_origin(plan)

    # canonicalise door names and drop duplicates / self-doors
    names = {r["name"].lower(): r["name"] for r in plan["rooms"]}
    clean, seen = [], set()
    for d in plan["doors"]:
        a = _canon(plan, d["a"], names)
        b = OUTSIDE if d["b"].lower() == OUTSIDE else _canon(plan, d["b"], names)
        if a and b and a != b:
            key = tuple(sorted((a.lower(), b.lower())))
            if key not in seen:
                seen.add(key)
                clean.append({"a": a, "b": b})
    if len(clean) != len(plan["doors"]):
        fixes.append(f"cleaned door list ({len(plan['doors'])} -> {len(clean)})")
    # a door can only exist in a wall the two rooms actually share
    possible = []
    for d in clean:
        a, b = _door_rooms(plan, d)
        seg = exterior_wall(a, plan["rooms"]) if b is None else shared_wall(a, b)
        if seg and seg[3] - seg[2] >= MIN_DOOR_WALL:
            possible.append(d)
    if len(possible) != len(clean):
        fixes.append(f"dropped {len(clean) - len(possible)} door(s) between rooms that share no wall")
    plan["doors"] = possible

    fixes += _auto_doors(plan)
    return plan, fixes


def _canon(plan, name, names):
    if name.lower() in names:
        return names[name.lower()]
    try:
        return find_room(plan, name)["name"]
    except PlanError:
        return None


def _auto_doors(plan):
    """Give every unreachable room a door, preferring a reachable neighbour."""
    fixes = []
    if not any(d["b"] == OUTSIDE for d in plan["doors"]):
        def score(r):
            ext = exterior_wall(r, plan["rooms"])
            length = ext[3] - ext[2] if ext else 0
            entry = re.search(r"porch|entr|gate|garage|drawing|foyer", r["name"], re.I)
            return (length >= MIN_DOOR_WALL, bool(entry), -r["y"], length)
        best = max(plan["rooms"], key=score)
        plan["doors"].append({"a": best["name"], "b": OUTSIDE})
        fixes.append(f"no entrance found; added main door to {best['name']}")
    for _ in range(len(plan["rooms"])):
        stuck = unreachable(plan)
        if not stuck:
            break
        reach = {r["name"] for r in plan["rooms"]} - {r["name"] for r in stuck}
        added = False
        for r in stuck:
            nbrs = [o for o in plan["rooms"] if o["name"] in reach
                    and (sw := shared_wall(r, o)) and sw[3] - sw[2] >= MIN_DOOR_WALL]
            if nbrs:
                n = max(nbrs, key=lambda o: o["w"] * o["h"])
                plan["doors"].append({"a": n["name"], "b": r["name"]})
                fixes.append(f"{r['name']} had no way in; added a door from {n['name']}")
                added = True
                break
        if not added:
            break
    return fixes


# ---------------------------------------------------------------- edit operations

SIDE_ALIASES = {
    "east": "east", "right": "east", "e": "east",
    "west": "west", "left": "west", "w": "west",
    "north": "north", "top": "north", "front": "north", "up": "north", "n": "north",
    "south": "south", "bottom": "south", "back": "south", "down": "south", "rear": "south", "s": "south",
}


def _side(s, default="east"):
    return SIDE_ALIASES.get(str(s or default).strip().lower(), default)


def _push(plan, axis, line, delta, forward):
    """Insert (delta>0) or remove (delta<0) a strip of space across the whole house
    at `line`. forward=True moves everything at/after the line, else at/before it.
    Rooms that end on the line or span it stretch, so the plan stays gap-free."""
    lo_k, len_k = ("x", "w") if axis == "x" else ("y", "h")
    for r in plan["rooms"]:
        a, b = r[lo_k], r[lo_k] + r[len_k]
        a, b = _map(a, line, delta, forward), _map(b, line, delta, forward)
        r[lo_k], r[len_k] = a, b - a


def _map(c, line, delta, forward):
    if forward:
        if delta >= 0:
            return c + delta if c >= line - EPS else c
        if c >= line - EPS:
            return c + delta
        return line + delta if c > line + delta else c  # collapse into the removed strip
    if delta >= 0:
        return c - delta if c <= line + EPS else c
    if c <= line + EPS:
        return c - delta
    return line - delta if c < line - delta else c


def _resize(plan, room, side, by):
    r = find_room(plan, room)
    side = _side(side)
    by = float(by)
    if side == "east":
        _push(plan, "x", r["x"] + r["w"], by, True)
    elif side == "south":
        _push(plan, "y", r["y"] + r["h"], by, True)
    elif side == "west":
        _push(plan, "x", r["x"], by, False)
    else:
        _push(plan, "y", r["y"], by, False)
    return f"{r['name']} {'grew' if by > 0 else 'shrank'} {abs(by):g} ft on the {side} side"


def _add_room(plan, name, w, h, next_to, side):
    name = str(name or "New Room").strip()
    if any(r["name"].lower() == name.lower() for r in plan["rooms"]):
        raise PlanError(f"a room called '{name}' already exists")
    n = find_room(plan, next_to)
    side = _side(side)
    w, h = float(w or 8), float(h or 8)
    if side in ("east", "west"):
        h = min(h, n["h"]) if h > n["h"] else h
        x = n["x"] + n["w"] if side == "east" else n["x"] - w
        new = {"name": name, "x": x, "y": n["y"], "w": w, "h": h}
    else:
        w = min(w, n["w"]) if w > n["w"] else w
        y = n["y"] + n["h"] if side == "south" else n["y"] - h
        new = {"name": name, "x": n["x"], "y": y, "w": w, "h": h}
    if _collides(plan, new):
        # make room by inserting a strip of space next to the neighbour
        axis = "x" if side in ("east", "west") else "y"
        size = w if axis == "x" else h
        line = {"east": n["x"] + n["w"], "west": n["x"], "south": n["y"] + n["h"], "north": n["y"]}[side]
        band = (new["y"], new["y"] + new["h"]) if axis == "x" else (new["x"], new["x"] + new["w"])
        _insert_strip(plan, axis, line, size, side in ("east", "south"), band)
        n = find_room(plan, n["name"])
        # fill the whole strip beside the neighbour so no hole is left behind
        if axis == "x":
            new["y"], new["h"] = n["y"], n["h"]
        else:
            new["x"], new["w"] = n["x"], n["w"]
        w, h = new["w"], new["h"]
        if side == "east":
            new["x"] = n["x"] + n["w"]
        elif side == "west":
            new["x"] = n["x"] - w
        elif side == "south":
            new["y"] = n["y"] + n["h"]
        else:
            new["y"] = n["y"] - h
    plan["rooms"].append(new)
    plan["doors"].append({"a": n["name"], "b": name})
    _translate_to_origin(plan)
    return f"added {name} ({w:g}x{h:g} ft) on the {side} side of {n['name']}"


def _insert_strip(plan, axis, line, size, forward, band):
    """Like _push, but rooms inside `band` that merely end on the line (the
    neighbour) keep their size, so the new room slots in beside them."""
    lo_k, len_k = ("x", "w") if axis == "x" else ("y", "h")
    blo_k, blen_k = ("y", "h") if axis == "x" else ("x", "w")
    for r in plan["rooms"]:
        in_band = r[blo_k] < band[1] - EPS and r[blo_k] + r[blen_k] > band[0] + EPS
        a, b = r[lo_k], r[lo_k] + r[len_k]
        if forward:
            if in_band:
                a = a + size if a >= line - EPS else a
                b = b + size if b > line + EPS else b
            else:
                a = a + size if a >= line - EPS else a
                b = b + size if b >= line - EPS else b
        else:
            if in_band:
                a = a - size if a < line - EPS else a
                b = b - size if b <= line + EPS else b
            else:
                a = a - size if a <= line + EPS else a
                b = b - size if b <= line + EPS else b
        r[lo_k], r[len_k] = a, b - a


def _collides(plan, new):
    nx1, ny1, nx2, ny2 = _box(new)
    for r in plan["rooms"]:
        x1, y1, x2, y2 = _box(r)
        if _overlap_1d(nx1, nx2, x1, x2) * _overlap_1d(ny1, ny2, y1, y2) > 1.0:
            return True
    return False


def _rename_in_doors(plan, old, new):
    for d in plan["doors"]:
        for k in ("a", "b"):
            if d[k].lower() == old.lower():
                d[k] = new


def apply_ops(plan, ops):
    """Apply model-proposed ops to a copy of the plan. Returns (plan, notes)."""
    plan = copy.deepcopy(plan)
    before = {r["name"]: (r["w"], r["h"]) for r in plan["rooms"]}
    notes = []
    for op in ops:
        kind = str(op.get("op", "")).lower()
        if kind == "resize":
            notes.append(_resize(plan, op.get("room"), op.get("side"), op.get("by", 2)))
        elif kind == "set_size":
            r = find_room(plan, op.get("room"))
            if op.get("w") is not None and abs(float(op["w"]) - r["w"]) > EPS:
                notes.append(_resize(plan, r["name"], "east", float(op["w"]) - r["w"]))
            r = find_room(plan, r["name"])
            if op.get("h") is not None and abs(float(op["h"]) - r["h"]) > EPS:
                notes.append(_resize(plan, r["name"], "south", float(op["h"]) - r["h"]))
        elif kind == "add_room":
            notes.append(_add_room(plan, op.get("name"), op.get("w"), op.get("h"), op.get("next_to"), op.get("side")))
        elif kind == "remove_room":
            r = find_room(plan, op.get("room"))
            plan["rooms"].remove(r)
            plan["doors"] = [d for d in plan["doors"] if r["name"].lower() not in (d["a"].lower(), d["b"].lower())]
            notes.append(f"removed {r['name']}")
        elif kind == "rename":
            r = find_room(plan, op.get("room"))
            new = str(op.get("to") or "").strip()
            if not new:
                raise PlanError("rename needs 'to'")
            _rename_in_doors(plan, r["name"], new)
            notes.append(f"renamed {r['name']} to {new}")
            r["name"] = new
        elif kind == "swap":
            a, b = find_room(plan, op.get("a")), find_room(plan, op.get("b"))
            tmp = "\0swap"
            _rename_in_doors(plan, a["name"], tmp)
            _rename_in_doors(plan, b["name"], a["name"])
            _rename_in_doors(plan, tmp, b["name"])
            a["name"], b["name"] = b["name"], a["name"]
            notes.append(f"swapped {b['name']} and {a['name']}")
        elif kind == "add_door":
            a = find_room(plan, op.get("a"))["name"]
            b = OUTSIDE if str(op.get("b", "")).lower() == OUTSIDE else find_room(plan, op.get("b"))["name"]
            plan["doors"].append({"a": a, "b": b})
            notes.append(f"added a door between {a} and {b}")
        elif kind == "remove_door":
            a = find_room(plan, op.get("a"))["name"].lower()
            b = OUTSIDE if str(op.get("b", "")).lower() == OUTSIDE else find_room(plan, op.get("b"))["name"].lower()
            before = len(plan["doors"])
            plan["doors"] = [d for d in plan["doors"] if {d["a"].lower(), d["b"].lower()} != {a, b}]
            if len(plan["doors"]) == before:
                raise PlanError(f"there is no door between {op.get('a')} and {op.get('b')}")
            notes.append(f"removed the door between {op.get('a')} and {op.get('b')}")
        else:
            raise PlanError(f"unknown op '{kind}'")
    _translate_to_origin(plan)
    for r in plan["rooms"]:
        for k in ("x", "y", "w", "h"):
            r[k] = round(r[k], 2)
    # doors whose wall disappeared are dropped; repair() re-routes access later
    kept = []
    for d in plan["doors"]:
        a, b = _door_rooms(plan, d)
        seg = None if a is None else (exterior_wall(a, plan["rooms"]) if b is None else shared_wall(a, b))
        if seg and seg[3] - seg[2] >= MIN_DOOR_WALL:
            kept.append(d)
        else:
            notes.append(f"removed door {d['a']} <-> {d['b']} (they no longer share a wall)")
    plan["doors"] = kept
    touched = " ".join(notes)
    also = [r["name"] for r in plan["rooms"] if r["name"] in before
            and before[r["name"]] != (r["w"], r["h"]) and r["name"] not in touched]
    if also:
        notes.append("also stretched to keep walls aligned: " + ", ".join(also))
    return plan, notes


# ---------------------------------------------------------------- geometry + stats

def geometry(plan):
    """Turn rooms into merged wall segments with door openings cut out."""
    rooms = plan["rooms"]
    lines = {}
    for r in rooms:
        for axis, c, lo, hi in _edges(r):
            lines.setdefault((axis, round(c, 2)), []).append((lo, hi))
    doors = []
    for d in plan["doors"]:
        a, b = _door_rooms(plan, d)
        if a is None:
            continue
        seg = exterior_wall(a, rooms) if b is None else shared_wall(a, b)
        if not seg or seg[3] - seg[2] < MIN_DOOR_WALL:
            continue
        axis, c, lo, hi = seg
        width = min(DOOR_WIDTH, hi - lo - 1.0)
        mid = (lo + hi) / 2
        doors.append({"axis": axis, "c": c, "lo": mid - width / 2, "hi": mid + width / 2,
                      "a": a["name"], "b": b["name"] if b else OUTSIDE, "main": b is None})
    walls = []
    for (axis, c), ivs in lines.items():
        ivs.sort()
        merged = [list(ivs[0])]
        for lo, hi in ivs[1:]:
            if lo <= merged[-1][1] + EPS:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        segs = [tuple(m) for m in merged]
        for dr in doors:
            if dr["axis"] == axis and abs(dr["c"] - c) < EPS:
                segs = _subtract(segs, dr["lo"], dr["hi"])
        for lo, hi in segs:
            if hi - lo > EPS:
                walls.append({"axis": axis, "c": c, "lo": lo, "hi": hi})
    return {"walls": walls, "doors": doors}


def stats(plan, sqft_per_marla=SQFT_PER_MARLA):
    xs = [r["x"] + r["w"] for r in plan["rooms"]]
    ys = [r["y"] + r["h"] for r in plan["rooms"]]
    covered = sum(r["w"] * r["h"] for r in plan["rooms"])
    footprint = max(xs) * max(ys)
    return {"covered_sqft": round(covered), "footprint_w": max(xs), "footprint_h": max(ys),
            "footprint_sqft": round(footprint), "marla": round(footprint / sqft_per_marla, 1),
            "rooms": len(plan["rooms"])}
