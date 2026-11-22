"""Independent expected decisions and counterexamples for the finite rule audit."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from risklab.rule_evidence import compile_rule, fixtures, main, run_study, snapshot


WIND = {"flag": "gust"}
ROOF = {"flag": "roof_open"}
FOG = {"flag": "fog"}
UNKNOWN = {"unmapped": "port"}


class RuleEvidenceTests(unittest.TestCase):
    def test_alternative_flags_are_not_a_joint_path_even_when_both_are_true(self):
        rule = compile_rule({"any": [WIND, ROOF]})
        self.assertTrue(rule.both_referenced)
        self.assertFalse(rule.jointly_possible)
        self.assertEqual(rule.replay({"gust": True, "roof_open": True}),
                         {"pause": True, "pair_path_active": False})

    def test_signed_conditions_and_contradictions(self):
        for expr in [{"all": [WIND, ROOF, {"not": WIND}]},
                     {"all": [WIND, {"not": ROOF}]}]:
            rule = compile_rule(expr)
            self.assertTrue(rule.both_referenced)
            self.assertFalse(rule.jointly_possible)
        impossible = compile_rule({"all": [WIND, {"not": WIND}]})
        self.assertFalse(impossible.replay({"gust": True})["pause"])

    def test_distributive_paths_agree_with_independent_truth_table(self):
        # not(not gust or (not roof and not fog)) is gust and (roof or fog).
        rule = compile_rule({"not": {"any": [{"not": WIND}, {"all": [{"not": ROOF}, {"not": FOG}]}]}})
        self.assertTrue(rule.jointly_possible)
        for wind, roof, fog in itertools.product((True, False), repeat=3):
            out = rule.replay({"gust": wind, "roof_open": roof, "fog": fog})
            self.assertEqual(out, {"pause": wind and (roof or fog), "pair_path_active": wind and roof})

    def test_compiled_snapshot_survives_edits_to_input_and_exported_tree(self):
        expression = {"all": [{"flag": "gust"}, {"flag": "roof_open"}]}
        rule = compile_rule(expression)
        sensor = {"gust": True, "roof_open": True, "fog": False}
        expression["all"][1]["flag"] = "fog"
        rule.expression["all"].clear()
        self.assertEqual(rule.expression, {"all": [WIND, ROOF]})
        self.assertEqual(rule.replay(sensor), {"pause": True, "pair_path_active": True})
        self.assertFalse(compile_rule(expression).replay(sensor)["pause"])
        partial = compile_rule({"all": [WIND, UNKNOWN]})
        mapping, paths = partial.completions[0]
        with self.assertRaises(TypeError):
            mapping["port"] = "fog"
        self.assertIsInstance(paths, frozenset)

    def test_partial_mapping_does_not_discard_other_evidence(self):
        rule = compile_rule({"any": [WIND, UNKNOWN]})
        self.assertIsNone(rule.both_referenced)
        self.assertFalse(rule.jointly_possible)
        self.assertIs(rule.replay({"gust": True})["pause"], True)
        joint = compile_rule({"all": [WIND, UNKNOWN]})
        self.assertIsNone(joint.jointly_possible)
        same_alias = compile_rule({"all": [WIND, UNKNOWN, {"not": UNKNOWN}]})
        self.assertFalse(same_alias.jointly_possible)
        self.assertIs(same_alias.replay({"gust": True, "roof_open": False, "fog": True})["pause"], False)

    def test_missing_signal_respects_decisive_known_sibling(self):
        rule = compile_rule({"all": [WIND, ROOF]})
        self.assertEqual(rule.replay({"roof_open": True}), {"pause": None, "pair_path_active": None})
        self.assertEqual(rule.replay({"roof_open": False}), {"pause": False, "pair_path_active": False})
        with self.assertRaises(ValueError):
            rule.replay({"roof_open": 1})

    def test_effective_version_and_future_changes(self):
        versions, _ = fixtures()
        north = lambda tick: next(row for row in snapshot(versions, tick) if row["id"] == "north")
        self.assertEqual(north(3)["from"], 1)
        self.assertEqual(north(4)["from"], 4)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            snapshot(versions + [versions[0]], 6)

    def test_definitions_are_deduplicated_by_entity_and_by_template(self):
        result = run_study()
        by_rule = result["definition_support"]["per_rule"]
        by_template = result["definition_support"]["per_template"]
        self.assertEqual(by_rule["both_referenced"]["unknown"], 1)
        self.assertEqual(by_rule["jointly_possible"]["yes_per_known"], 2 / 7)
        self.assertEqual(by_template["jointly_possible"]["yes_per_known"], 1 / 6)
        self.assertEqual(by_template["both_referenced"]["known_denominator"], 5)
        replay = result["replay_support"]["pair_path_active"]
        self.assertEqual((replay["yes"], replay["no"], replay["unknown"]), (3, 36, 2))
        # At minute 2 only the annex has a satisfied joint path; north changes at minute 4.
        hits = {(r["tick"], r["id"]) for r in result["replay"] if r["pair_path_active"] is True}
        self.assertEqual(hits, {(2, "annex"), (5, "north"), (5, "annex")})
        self.assertEqual(len(result["replay"]), 41)

    def test_cli_persists_evidence_in_workspace_and_rejects_outside(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as allowed, tempfile.TemporaryDirectory() as outside:
            output = Path(allowed) / "experiment.json"
            with patch("sys.argv", ["rule_evidence", "--out", str(output)]):
                main()
            self.assertEqual(json.loads(output.read_text()), run_study())
            output = Path(outside) / "experiment.json"
            with patch("sys.argv", ["rule_evidence", "--out", str(output)]):
                with self.assertRaisesRegex(ValueError, "escapes"):
                    main()
            self.assertFalse(output.exists())

    def test_input_grammar_and_repeated_reference(self):
        for expr in ({"all": []}, {"flag": "made_up"}, {"script": "unexpected"},
                     {"flag": "gust", "extra": None},
                     {"all": [{"unmapped": key} for key in ("x", "y", "z")]}):
            with self.assertRaises(ValueError):
                compile_rule(expr)
        repeat = compile_rule({"all": [WIND, WIND]})
        self.assertFalse(repeat.both_referenced)
        self.assertFalse(repeat.jointly_possible)
