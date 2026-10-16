"""Readable simulator: hidden propensity is never written or supplied to a model."""
import numpy as np
import pandas as pd

DAY = 86400
ORIGIN = 1767225600  # 2026-01-01T00:00:00Z, fictional experiment clock


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def simulate(config):
    rng = np.random.default_rng(config["seed"])
    days = config["days"]
    user_count = 540
    # Account birth introduces genuinely unseen subjects in later windows.
    birth_day = np.concatenate([np.full(150, -30), rng.integers(0, days, user_count - 150)])
    hidden_user = rng.normal(0, 0.8, user_count)
    rows, labels = [], []
    order_times = np.sort(rng.uniform(0, days - 0.05, config["orders"]))
    for order_idx, day in enumerate(order_times):
        eligible = np.flatnonzero(birth_day <= day)
        user = int(rng.choice(eligible))
        order_amount = float(np.clip(rng.lognormal(3.4, 0.95), 2, 1300))
        device_age = max(0., rng.exponential(30) - 10 * max(hidden_user[user], 0))
        attempts = int(rng.choice([1, 2, 3], p=[0.70, 0.23, 0.07]))
        for attempt in range(attempts):
            # A second attempt belongs to the same order; user-level pairing may not.
            t = ORIGIN + int(day * DAY) + attempt * int(rng.integers(30, 1200))
            if t >= ORIGIN + days * DAY:
                continue
            amount = float(np.clip(order_amount * rng.uniform(0.88, 1.12), 2, 1500))
            age = (t - ORIGIN) / DAY - birth_day[user]
            auth = int(rng.choice([0, 1, 2], p=[0.20, 0.52, 0.28]))
            geo = float(np.clip(rng.beta(1.3, 4.0) + 0.08 * hidden_user[user], 0, 1))
            # Missingness depends on the independent ingestion source, not labels.
            source = str(rng.choice(["stream_a", "stream_b"]))
            geo_observed = np.nan if rng.random() < (0.10 if source == "stream_a" else 0.17) else geo
            # Existing score has a fixed noisy mechanism; no labels are used to fit it.
            score = float(sigmoid(-2.0 + 0.40 * np.log1p(amount) + 0.8 * np.exp(-age / 15)
                                  + 0.6 * np.exp(-device_age / 10) - 0.6 * auth + rng.normal(0, 0.6)))
            # Risk is a Bernoulli latent outcome, not a rewrite of any displayed rule.
            # Smooth effects, unobserved subject/noise, and mild later drift coexist.
            logit = (-4.2 + 0.30 * np.log1p(amount) + hidden_user[user]
                     + 1.3 * np.exp(-device_age / 12) + 1.0 * np.exp(-age / 20)
                     + 1.0 * geo - 0.65 * auth + 0.25 * (day >= 75) + rng.normal(0, 0.4))
            risk = int(rng.random() < sigmoid(logit))
            # Simulation policy v1. Priority: decline, then review, then approve.
            decline = amount > 210 and auth == 0
            review = (score > 0.58) and not decline
            action = "decline" if decline else "review" if review else "approve"
            # Review has no protective effect in this simulator; rail failure is separate.
            payment = int(action != "decline" and rng.random() < (0.91 - 0.10 * risk))
            event_id = f"e{len(rows):07d}"
            rows.append(dict(event_id=event_id, order_id=f"o{order_idx:07d}", user_id=f"u{user:04d}",
                             device_id=f"d{user:04d}_{order_idx % 7}", domain="fictional_wallet",
                             decision_ts=t, available_ts=t-1, amount=amount,
                             account_age_days=age, device_age_days=device_age, auth_strength=auth,
                             geo_distance=geo_observed, prior_score=score, source=source,
                             policy_version="synthetic_v1", action=action, payment_result=payment,
                             result_ts=t+15))
            # Idealized independent audit makes attempted risk observable even for declines.
            labels.append(dict(event_id=event_id, risk_label=risk,
                               label_available_ts=t+int(rng.integers(2, 8))*DAY))
    return (pd.DataFrame(rows).sort_values(["decision_ts", "event_id"]).reset_index(drop=True),
            pd.DataFrame(labels))
