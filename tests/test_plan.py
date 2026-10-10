"""Unit tests for the plan engine (no model needed).  Run:  python -m unittest -v"""
import json
import unittest
from pathlib import Path

from server import plan as P

SAMPLE = json.loads((Path(__file__).resolve().parent.parent / "samples" / "ten_marla.json").read_text())


class CheckerTests(unittest.TestCase):
    def test_sample_is_valid_and_reachable(self):
        self.assertEqual(P.validate(SAMPLE), [])
        self.assertEqual(P.unreachable(SAMPLE), [])

    def test_overlap_detected(self):
        p = {"rooms": [{"name": "A", "x": 0, "y": 0, "w": 10, "h": 10},
                       {"name": "B", "x": 5, "y": 0, "w": 10, "h": 10}], "doors": []}
        self.assertIn("overlap", [e["code"] for e in P.validate(p)])

    def test_door_between_non_neighbours_detected(self):
        p = {"rooms": [{"name": "A", "x": 0, "y": 0, "w": 10, "h": 10},
                       {"name": "B", "x": 20, "y": 0, "w": 10, "h": 10}], "doors": [{"a": "A", "b": "B"}]}
        self.assertIn("door_not_adjacent", [e["code"] for e in P.validate(p)])

    def test_duplicate_names_detected(self):
        p = {"rooms": [{"name": "Bedroom", "x": 0, "y": 0, "w": 10, "h": 10},
                       {"name": "bedroom", "x": 10, "y": 0, "w": 10, "h": 10}], "doors": []}
        self.assertIn("dup_name", [e["code"] for e in P.validate(p)])

    def test_bad_schema_rejected(self):
        with self.assertRaises(P.PlanError):
            P.normalise({"rooms": [{"name": "A", "x": "?", "y": 0, "w": 1, "h": 1}]})


class RepairTests(unittest.TestCase):
    def test_snap_closes_near_miss_gaps(self):
        messy = P.normalise({"rooms": [
            {"name": "Kitchen", "x": 0.3, "y": 0, "w": 11.6, "h": 12},
            {"name": "Lounge", "x": 12.4, "y": 0.2, "w": 15, "h": 12}],
            "doors": [{"a": "kitchen", "b": "Lounge"}]})
        self.assertTrue(P.validate(messy))           # door wall missing before repair
        fixed, fixes = P.repair(messy)
        self.assertEqual(P.validate(fixed), [])
        self.assertIsNotNone(P.shared_wall(fixed["rooms"][0], fixed["rooms"][1]))

    def test_auto_doors_make_every_room_reachable(self):
        p = {"rooms": [{"name": "A", "x": 0, "y": 0, "w": 10, "h": 10},
                       {"name": "B", "x": 10, "y": 0, "w": 10, "h": 10},
                       {"name": "C", "x": 20, "y": 0, "w": 10, "h": 10}], "doors": []}
        fixed, fixes = P.repair(p)
        self.assertEqual(P.unreachable(fixed), [])
        self.assertTrue(fixes)


class EditTests(unittest.TestCase):
    def assertValid(self, plan):
        self.assertEqual(P.validate(plan), [])

    def test_resize_grows_room_and_keeps_plan_valid(self):
        p, _ = P.apply_ops(SAMPLE, [{"op": "resize", "room": "kitchen", "by": 2}])
        self.assertEqual(P.find_room(p, "Kitchen")["w"], 14)
        self.assertEqual(P.find_room(p, "Lounge")["x"], 14)  # neighbour pushed, not overlapped
        self.assertValid(p)

    def test_shrink_from_north(self):
        p, _ = P.apply_ops(SAMPLE, [{"op": "resize", "room": "lounge", "side": "north", "by": -3}])
        self.assertEqual(P.find_room(p, "Lounge")["h"], 15)
        self.assertValid(p)

    def test_add_room_outside_edge(self):
        p, _ = P.apply_ops(SAMPLE, [{"op": "add_room", "name": "Bath 2", "w": 7, "h": 8,
                                     "next_to": "Bedroom 2", "side": "east"}])
        self.assertValid(p)
        self.assertEqual(P.unreachable(p), [])

    def test_add_room_inside_inserts_strip(self):
        p, notes = P.apply_ops(SAMPLE, [{"op": "add_room", "name": "Store", "w": 6, "h": 8,
                                         "next_to": "Kitchen", "side": "east"}])
        p, _ = P.repair(p)
        self.assertValid(p)
        self.assertEqual(P.unreachable(p), [])

    def test_swap_and_rename_update_doors(self):
        p, _ = P.apply_ops(SAMPLE, [{"op": "swap", "a": "Kitchen", "b": "Bedroom 1"},
                                    {"op": "rename", "room": "Lawn", "to": "Sehan"}])
        self.assertValid(p)
        self.assertTrue(any(d["b"] == "Sehan" or d["a"] == "Sehan" for d in p["doors"]))

    def test_fuzzy_room_names(self):
        self.assertEqual(P.find_room(SAMPLE, "drawing")["name"], "Drawing Room")
        self.assertEqual(P.find_room(SAMPLE, "bedrom 2")["name"], "Bedroom 2")
        with self.assertRaises(P.PlanError):
            P.find_room(SAMPLE, "garage")

    def test_unknown_op_rejected(self):
        with self.assertRaises(P.PlanError):
            P.apply_ops(SAMPLE, [{"op": "teleport"}])


class GeometryTests(unittest.TestCase):
    def test_every_door_cuts_an_opening(self):
        g = P.geometry(SAMPLE)
        self.assertEqual(len(g["doors"]), len(SAMPLE["doors"]))
        for d in g["doors"]:
            for w in g["walls"]:
                if w["axis"] == d["axis"] and abs(w["c"] - d["c"]) < P.EPS:
                    overlap = min(w["hi"], d["hi"]) - max(w["lo"], d["lo"])
                    self.assertLessEqual(overlap, P.EPS, f"wall covers door {d}")

    def test_stats(self):
        s = P.stats(SAMPLE)
        self.assertEqual(s["covered_sqft"], 35 * 65)
        self.assertAlmostEqual(s["marla"], 10.1)


class PlannerTests(unittest.TestCase):
    SAMPLES = ["ten_marla", "five_marla", "seven_marla", "one_kanal"]

    def plans(self):
        root = Path(__file__).resolve().parent.parent / "samples"
        for name in self.SAMPLES:
            yield name, P.plan_circulation(json.loads((root / f"{name}.json").read_text()))

    def test_one_gate_on_the_porch_and_no_kitchen_off_the_garage(self):
        for name, (plan, _) in self.plans():
            g = P.geometry(plan)
            gates = [d for d in g["doors"] if d["kind"] == "gate"]
            self.assertEqual([d["a"] for d in gates], ["Car Porch"], name)
            self.assertTrue(gates[0]["main"], name)
            self.assertGreaterEqual(gates[0]["hi"] - gates[0]["lo"], 8, name)
            pairs = {frozenset((P.room_kind(P.find_room(plan, d["a"])), P.room_kind(P.find_room(plan, d["b"]))))
                     for d in plan["doors"] if d["b"] != P.OUTSIDE}
            self.assertNotIn(frozenset(("porch", "kitchen")), pairs, name)
            self.assertIn(frozenset(("porch", "drawing")), pairs, name)  # guest entrance

    def test_planned_plans_stay_valid_reachable_and_stable(self):
        for name, (plan, _) in self.plans():
            self.assertEqual(P.validate(plan), [], name)
            self.assertEqual(P.unreachable(plan), [], name)
            self.assertEqual(P.plan_circulation(plan)[1], [], f"{name}: second pass should change nothing")


if __name__ == "__main__":
    unittest.main()
