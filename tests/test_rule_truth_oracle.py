"""Independent truth-table checks for the bounded observatory rule grammar."""
import itertools
import random
import unittest

from risklab.rule_evidence import compile_rule


SENSORS = ("gust", "roof_open", "fog")
FOCUS_PAIR = {"gust", "roof_open"}
TRUTH_VALUES = (False, None, True)


def rule_sample():
    """Generate the same 70 depth-limited expressions for both checks."""
    rng = random.Random(102)
    leaves = [{"flag": name} for name in SENSORS] + [{"unmapped": name} for name in "ab"]

    def draw(depth):
        if depth == 0 or rng.random() < 0.38:
            return rng.choice(leaves)
        operator = rng.choice(("all", "any", "not"))
        if operator == "not":
            return {"not": draw(depth - 1)}
        return {operator: [draw(depth - 1), draw(depth - 1)]}

    return [draw(3) for _ in range(70)]


def possible_bindings():
    return [dict(a=a, b=b) for a, b in itertools.product(SENSORS, repeat=2)]


def positive_witnesses(node, event, binding, desired=True):
    """Prove the desired outcome on this observed event and record positive leaves used."""
    op, value = next(iter(node.items()))
    if op == "not":
        return positive_witnesses(value, event, binding, not desired)
    if op in ("flag", "unmapped"):
        name = value if op == "flag" else binding[value]
        if event[name] != desired:
            return []
        return [{name} if desired else set()]

    children = [positive_witnesses(child, event, binding, desired) for child in value]
    if (op == "any" and desired) or (op == "all" and not desired):
        return [proof for alternatives in children for proof in alternatives]
    return [set().union(*group) for group in itertools.product(*children)]


def truth_rank(node, event, binding):
    """Evaluate using the chain false < unknown < true, independently of the production evaluator."""
    op, value = next(iter(node.items()))
    if op in ("flag", "unmapped"):
        return event[value if op == "flag" else binding[value]]
    if op == "not":
        return 2 - truth_rank(value, event, binding)
    ranks = [truth_rank(child, event, binding) for child in value]
    return min(ranks) if op == "all" else max(ranks)


def unanimous(values):
    return next(iter(values)) if len(values) == 1 else None


class RuleTruthOracleTests(unittest.TestCase):
    def test_complete_events_against_constructive_proofs(self):
        bindings = possible_bindings()
        checked = 0
        for expression in rule_sample():
            compiled = compile_rule(expression)
            for values in itertools.product((True, False), repeat=len(SENSORS)):
                event = dict(zip(SENSORS, values))
                proofs = [positive_witnesses(expression, event, b) for b in bindings]
                # An empty proof set means TRUE supplied only by negative literals.
                # An empty list means no proof of TRUE exists for this binding.
                pause = unanimous({bool(paths) for paths in proofs})
                pair = unanimous({any(FOCUS_PAIR <= path for path in paths) for paths in proofs})
                with self.subTest(expression=expression, event=event):
                    self.assertEqual(compiled.replay(event), {"pause": pause, "pair_path_active": pair})
                checked += 1
        self.assertEqual(checked, 560)

    def test_partial_events_against_three_valued_lattice(self):
        bindings = possible_bindings()
        checked = 0
        for expression in rule_sample():
            compiled = compile_rule(expression)
            for values in itertools.product(range(3), repeat=len(SENSORS)):
                ranks = dict(zip(SENSORS, values))
                event = {name: TRUTH_VALUES[value] for name, value in ranks.items()}
                expected = unanimous({TRUTH_VALUES[truth_rank(expression, ranks, b)] for b in bindings})
                with self.subTest(expression=expression, event=event):
                    self.assertIs(compiled.replay(event)["pause"], expected)
                checked += 1
        self.assertEqual(checked, 1890)
