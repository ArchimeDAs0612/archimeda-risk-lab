"""Keys, as-of SQL construction, temporal splits and exploratory case pairing."""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from .generate import DAY, ORIGIN


class AdmissionError(ValueError):
    pass


def assert_unique(frame, key, name):
    if key not in frame or frame[key].isna().any() or frame[key].duplicated().any():
        raise AdmissionError(f"{name}: missing or duplicate {key}; join multiplication blocked")


def build_samples(events, labels):
    required_events = {"event_id", "user_id", "decision_ts", "action", "result_ts"}
    required_labels = {"event_id", "risk_label", "label_available_ts"}
    if not required_events.issubset(events) or not required_labels.issubset(labels):
        raise AdmissionError("missing required event/label schema")
    assert_unique(events, "event_id", "events")
    assert_unique(labels, "event_id", "labels")
    if events.decision_ts.isna().any():
        raise AdmissionError("missing decision timestamp; temporal conclusions blocked")
    with sqlite3.connect(":memory:") as db:
        events.to_sql("events", db, index=False)
        db.execute("CREATE INDEX event_time ON events(user_id,decision_ts)")
        sample = pd.read_sql_query(Path(__file__).with_name("sample.sql").read_text(), db)
    sample = sample.merge(labels, on="event_id", how="left", validate="one_to_one")
    if len(sample) != len(events):
        raise AdmissionError("join changed sample grain")
    return sample


def split_samples(sample, config):
    t = sample.decision_ts
    observed = sample.risk_label.notna()
    train = (t < ORIGIN + config["train_end_day"]*DAY) & (sample.label_available_ts <= ORIGIN + config["train_asof_day"]*DAY)
    select = (t >= ORIGIN + config["select_start_day"]*DAY) & (t < ORIGIN + config["select_end_day"]*DAY) & (sample.label_available_ts <= ORIGIN + config["select_asof_day"]*DAY)
    test = (t >= ORIGIN + config["test_start_day"]*DAY) & (sample.label_available_ts <= ORIGIN + config["evaluation_asof_day"]*DAY)
    parts = {k: sample.loc[v & observed].copy() for k, v in [("train", train), ("select", select), ("test", test)]}
    ids = [set(v.event_id) for v in parts.values()]
    if any(ids[i] & ids[j] for i in range(3) for j in range(i+1, 3)):
        raise AdmissionError("overlapping evaluation windows")
    if any(len(v) == 0 or v.risk_label.isna().any() or v.risk_label.nunique() != 2 for v in parts.values()):
        raise AdmissionError("each window needs observed mature binary labels of both classes")
    if not parts["train"].decision_ts.max() < parts["select"].decision_ts.min() < parts["test"].decision_ts.min():
        raise AdmissionError("windows are not strictly ordered")
    if not (parts["train"].label_available_ts.max() <= ORIGIN + config["train_asof_day"]*DAY <= parts["select"].decision_ts.min()
            and parts["select"].label_available_ts.max() <= ORIGIN + config["select_asof_day"]*DAY <= parts["test"].decision_ts.min()):
        raise AdmissionError("labels not mature at training/selection freeze")
    return parts


def pair_cases(events, window_hours):
    """Earliest later successful payment by same user, many-to-one; not same order assumed."""
    with sqlite3.connect(":memory:") as db:
        events.to_sql("events", db, index=False)
        db.execute("CREATE INDEX pair_idx ON events(user_id,decision_ts)")
        pairs = pd.read_sql_query('''
        SELECT r.event_id AS reject_event, r.order_id AS reject_order, r.user_id,
          r.decision_ts AS reject_ts,
          (SELECT p.event_id FROM events p WHERE p.user_id=r.user_id
           AND p.payment_result=1 AND p.decision_ts>r.decision_ts
           AND p.decision_ts<=r.decision_ts+?
           ORDER BY p.decision_ts,p.event_id LIMIT 1) AS pass_event
        FROM events r WHERE r.action='decline'
        ''', db, params=[window_hours*3600])
    pairs = pairs.dropna(subset=["pass_event"])
    p = events[["event_id", "order_id", "decision_ts"]].rename(columns={"event_id":"pass_event", "order_id":"pass_order", "decision_ts":"pass_ts"})
    pairs = pairs.merge(p, on="pass_event", validate="many_to_one")
    pairs["gap_minutes"] = (pairs.pass_ts-pairs.reject_ts)/60
    pairs["same_order"] = pairs.pass_order == pairs.reject_order
    pairs["gap_band"] = pd.cut(pairs.gap_minutes, [0, 60, 360, 1440, np.inf], labels=["0-1h", "1-6h", "6-24h", ">24h"]).astype(str)
    return pairs


def condition_semantics(events, amount_threshold=210):
    """A∧B in one event differs from (∃A)∧(∃B) over order history."""
    flags = events.assign(a=events.amount>amount_threshold, b=events.auth_strength==0)
    agg = flags.assign(joint=flags.a & flags.b).groupby("order_id").agg(a=("a","max"), b=("b","max"), joint=("joint","max"))
    union = agg.a & agg.b
    return {"single_event_joint_orders":int(agg.joint.sum()), "cross_event_union_orders":int(union.sum()),
            "union_only_orders":agg.index[union & ~agg.joint].tolist()}
