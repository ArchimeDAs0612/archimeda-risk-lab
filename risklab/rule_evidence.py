"""Finite Boolean rule audit for a synthetic observatory, using the standard library."""
import argparse
import hashlib
import itertools
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Optional

from .study_contracts import workspace_path


FLAGS = ("gust", "roof_open", "fog")
PAIR = ("gust", "roof_open")


def fingerprint(value):
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def consensus(values):
    """All completions agree, or the result is unknown (None)."""
    options = set(values)
    return options.pop() if len(options) == 1 else None


def conjunction(values):
    return False if False in values else (None if None in values else True)


def disjunction(values):
    return True if True in values else (None if None in values else False)


def terminals(node, depth=0):
    """Validate the small JSON grammar before any enumeration."""
    if depth > 12 or not isinstance(node, dict) or len(node) != 1:
        raise ValueError("invalid or deeply nested expression")
    op, operand = next(iter(node.items()))
    if op == "flag" and operand in FLAGS:
        return [(op, operand)]
    if op == "unmapped" and isinstance(operand, str) and operand:
        return [(op, operand)]
    if op == "not":
        return terminals(operand, depth + 1)
    if op in ("any", "all") and isinstance(operand, list) and 1 <= len(operand) <= 8:
        leaves = []
        for child in operand:
            leaves.extend(terminals(child, depth + 1))
            if len(leaves) > 10:
                raise ValueError("expression exceeds ten leaves")
        return leaves
    raise ValueError("unknown operator, flag, or invalid arity")


def evaluate(node, binding, event):
    """Strong Kleene logic; an absent sensor reading is unknown."""
    op, operand = next(iter(node.items()))
    if op in ("flag", "unmapped"):
        return event.get(binding[operand] if op == "unmapped" else operand)
    if op == "not":
        value = evaluate(operand, binding, event)
        return None if value is None else not value
    values = [evaluate(child, binding, event) for child in operand]
    return conjunction(values) if op == "all" else disjunction(values)


def proof_paths(node, binding, positive=True):
    """Expand negation to signed leaves and enumerate conjunctions in the DNF."""
    op, operand = next(iter(node.items()))
    if op in ("flag", "unmapped"):
        name = binding[operand] if op == "unmapped" else operand
        return {frozenset([(name, positive)])}
    if op == "not":
        return proof_paths(operand, binding, not positive)
    children = [proof_paths(child, binding, positive) for child in operand]
    if (op == "any") == positive:
        return set().union(*children)
    paths = set()
    for parts in itertools.product(*children):
        terms = frozenset().union(*parts)
        if all((name, not sign) not in terms for name, sign in terms):
            paths.add(terms)
    return paths


def literal_value(event, term):
    name, sign = term
    value = event.get(name)
    return None if value is None else value == sign


@dataclass(frozen=True)
class CompiledRule:
    _expression_json: str
    # Each completion records an admissible mapping and its positive pair paths.
    completions: tuple
    both_referenced: Optional[bool]
    jointly_possible: Optional[bool]

    @property
    def expression(self):
        """Return an editable JSON view without changing the compiled definition."""
        return json.loads(self._expression_json)

    def replay(self, event):
        for key, value in event.items():
            if key not in FLAGS or (value is not None and type(value) is not bool):
                raise ValueError("invalid event flag or sensor value")
        actions, witnessed = [], []
        expression = self.expression
        for binding, paths in self.completions:
            actions.append(evaluate(expression, binding, event))
            witnessed.append(disjunction([
                conjunction([literal_value(event, term) for term in path]) for path in paths
            ]))
        return {"pause": consensus(actions), "pair_path_active": consensus(witnessed)}


def compile_rule(expression, pair=PAIR):
    if len(pair) != 2 or len(set(pair)) != 2 or any(flag not in FLAGS for flag in pair):
        raise ValueError("pair must name two different registered flags")
    leaves = terminals(expression)
    aliases = sorted({name for op, name in leaves if op == "unmapped"})
    if len(aliases) > 2:
        raise ValueError("at most two aliases supported")
    completions, references, permitted = [], [], []
    positives = {(name, True) for name in pair}
    for values in itertools.product(FLAGS, repeat=len(aliases)):
        binding = dict(zip(aliases, values))
        names = {binding[name] if op == "unmapped" else name for op, name in leaves}
        references.append(set(pair) <= names)
        paths = [terms for terms in proof_paths(expression, binding) if positives <= terms]
        permitted.append(bool(paths))
        completions.append((MappingProxyType(binding), frozenset(paths)))
    return CompiledRule(json.dumps(expression), tuple(completions), consensus(references), consensus(permitted))


def snapshot(rows, tick):
    """Select the latest effective definition per rule; reject ambiguous versions."""
    active = {}
    seen = set()
    for row in rows:
        key = row["id"], row["from"]
        if key in seen:
            raise ValueError("duplicate rule version")
        seen.add(key)
        previous = active.get(row["id"])
        if row["from"] <= tick and (previous is None or row["from"] > previous["from"]):
            active[row["id"]] = row
    return [active[key] for key in sorted(active)]


def support(results, key, weights):
    positive = sum(w for r, w in zip(results, weights) if r[key] is True)
    negative = sum(w for r, w in zip(results, weights) if r[key] is False)
    unknown = sum(w for r, w in zip(results, weights) if r[key] is None)
    known = positive + negative
    return {"yes": positive, "no": negative, "unknown": unknown, "known_denominator": known,
            "population": known + unknown, "yes_per_known": positive / known if known else None}


def fixtures():
    gust, roof, fog = ({"flag": name} for name in FLAGS)
    pair = {"all": [gust, roof]}
    definitions = [
        ("north", 1, {"any": [gust, roof]}), ("north", 4, pair),
        ("annex", 2, pair), ("fog_gate", 1, {"all": [gust, {"not": roof}]}),
        ("fallback", 1, {"any": [gust, {"unmapped": "spare"}]}),
        ("obstructed", 1, {"all": [gust, roof, {"not": gust}]}),
        ("fog_only", 1, fog), ("alternatives", 1, {"any": [gust, roof]}),
    ]
    versions = [{"id": name, "from": tick, "expression": expr} for name, tick, expr in definitions]
    readings = [(1, False, True, False), (2, True, True, False), (3, True, False, True),
                (4, False, True, False), (5, True, True, False), (6, None, True, False)]
    events = [{"tick": row[0], "sensors": dict(zip(FLAGS, row[1:]))} for row in readings]
    return versions, events


def run_study():
    versions, events = fixtures()
    freeze = max(x["tick"] for x in events)
    audit, replay = [], []
    compiled = {(row["id"], row["from"]): compile_rule(row["expression"]) for row in versions}
    for row in snapshot(versions, freeze):
        rule = compiled[row["id"], row["from"]]
        audit.append({"id": row["id"], "from": row["from"], "template": fingerprint(row["expression"]),
                      "both_referenced": rule.both_referenced, "jointly_possible": rule.jointly_possible})
    counts = Counter(x["template"] for x in audit)
    summary = {}
    for label, weights in (("per_rule", [1] * len(audit)),
                           ("per_template", [1 / counts[row["template"]] for row in audit])):
        summary[label] = {k: support(audit, k, weights) for k in ("both_referenced", "jointly_possible")}
    for event in events:
        for row in snapshot(versions, event["tick"]):
            result = compiled[row["id"], row["from"]].replay(event["sensors"])
            replay.append({"tick": event["tick"], "id": row["id"], "version_from": row["from"], **result})
    return {"study": "Synthetic observatory exposure interlock", "fixture_version": 1, "frozen_at": freeze,
            "input_sha256": fingerprint([versions, events, PAIR]), "focus_pair": list(PAIR),
            "rule_versions": versions, "events": events, "snapshot": audit, "definition_support": summary,
            "replay_support": {k: support(replay, k, [1] * len(replay)) for k in ("pause", "pair_path_active")},
            "replay": replay}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    output = workspace_path(parser.parse_args().out)
    result = run_study()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
