"""Train-only preprocessing, small models, exact complete-path replay."""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from scipy.special import expit


class Transform:
    def __init__(self, columns):
        self.columns = list(columns)
        self.names = self.columns + [f"{c}__missing" for c in self.columns]

    def fit(self, frame):
        values = frame[self.columns].to_numpy(dtype=float)
        self.medians = np.nanmedian(values, axis=0)
        if not np.isfinite(self.medians).all():
            raise ValueError("all-missing training feature")
        return self

    def apply(self, frame):
        x = frame[self.columns].to_numpy(dtype=float)
        missing = np.isnan(x)
        x = np.where(missing, self.medians, x)
        # sklearn tree inference uses float32. Replay uses exactly the same domain.
        return np.column_stack([x, missing.astype(float)]).astype(np.float32)

    def metadata(self):
        return {"input_columns":self.columns, "output_columns":self.names,
                "train_medians":dict(zip(self.columns, self.medians.tolist())),
                "missing":"replace by train median and append a missing indicator per input",
                "dtype":"float32", "fit_scope":"train only"}


def fit_model(train, columns, kind, config, seed=None):
    prep = Transform(columns).fit(train)
    x = prep.apply(train)
    scaler = None
    if kind == "lr":
        scaler = StandardScaler().fit(x)
        model = LogisticRegression(C=1.0, solver="liblinear", max_iter=1000, random_state=config["seed"])
        x = scaler.transform(x)
    elif kind == "tree":
        model = DecisionTreeClassifier(max_depth=config["tree_depth"], min_samples_leaf=config["min_leaf"],
                                       random_state=config["seed"] if seed is None else seed)
    else:
        raise ValueError(kind)
    model.fit(x, train.risk_label.astype(int))
    return {"prep":prep, "scaler":scaler, "model":model, "kind":kind}


def probabilities(bundle, frame):
    x = bundle["prep"].apply(frame)
    if bundle["scaler"] is not None:
        x = bundle["scaler"].transform(x)
    if bundle["kind"] == "lr":
        # Elementwise dot is mathematically identical; avoids vendor BLAS warnings
        # observed on one macOS NumPy build, without suppressing numerical warnings.
        model = bundle["model"]
        return expit(np.sum(x * model.coef_[0], axis=1) + model.intercept_[0])
    return bundle["model"].predict_proba(x)[:, 1]


def metrics(y, p, threshold):
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return {"n":0, "ap":None, "auc":None, "brier":None, "base_rate":None}
    pred = p >= threshold
    both = len(np.unique(y)) == 2
    return {"n":len(y), "positives":int(y.sum()), "base_rate":float(y.mean()),
            "ap":float(average_precision_score(y, p)) if both else None,
            "auc":float(roc_auc_score(y, p)) if both else None,
            "brier":float(brier_score_loss(y, p)), "threshold":float(threshold),
            "flagged":int(pred.sum()), "flagged_fraction":float(pred.mean()),
            "precision":float(y[pred].mean()) if pred.any() else None,
            "recall":float(y[pred].sum()/y.sum()) if y.sum() else None,
            "false_positive_rate":float(pred[y==0].mean()) if (y==0).any() else None}


def complete_paths(bundle):
    tree = bundle["model"].tree_
    names = bundle["prep"].names
    paths = []
    def walk(node, predicates):
        if tree.children_left[node] == tree.children_right[node]:
            paths.append({"leaf_id":int(node), "predicates":predicates,
                          "train_support":int(tree.n_node_samples[node])})
            return
        index = int(tree.feature[node])
        predicate = {"feature_index":index, "transformed_feature":names[index], "threshold":float(tree.threshold[node])}
        walk(tree.children_left[node], predicates+[dict(predicate, operator="<=")])
        walk(tree.children_right[node], predicates+[dict(predicate, operator=">")])
    walk(0, [])
    return paths


def replay_matrix(x, path):
    x = np.asarray(x, dtype=np.float32)
    mask = np.ones(len(x), dtype=bool)
    for term in path["predicates"]:
        values = x[:, term["feature_index"]]
        if term["operator"] == "<=":
            mask &= values <= term["threshold"]
        elif term["operator"] == ">":
            mask &= values > term["threshold"]
        else:
            raise ValueError("unknown predicate operator")
    return mask


def replay(bundle, frame, path):
    return replay_matrix(bundle["prep"].apply(frame), path)


def verify_membership(bundle, frame, paths):
    x = bundle["prep"].apply(frame)
    actual = bundle["model"].apply(x)
    for path in paths:
        if not np.array_equal(replay_matrix(x, path), actual == path["leaf_id"]):
            raise AssertionError(f"path {path['leaf_id']} replay diverges from model membership")
    return {"rows":len(frame), "leaves":len(paths), "all_paths_equal":True}


def choose_candidate(bundle, selection, config):
    """Selection labels choose one leaf. Final test never participates."""
    paths = complete_paths(bundle)
    ranked = []
    for path in paths:
        mask = replay(bundle, selection, path)
        n = int(mask.sum())
        if n >= config["candidate_min_select"]:
            ranked.append((float(selection.loc[mask, "risk_label"].mean()), n, -path["leaf_id"], path))
    if not ranked:
        # A real complete path is retained, with explicit insufficient support later.
        path = max(paths, key=lambda p:p["train_support"])
        return dict(path, selection_status="insufficient_selection_support")
    return dict(max(ranked, key=lambda item:item[:3])[3], selection_status="selected_for_investigation")


def calibration(y, p):
    result = []
    y, p = np.asarray(y), np.asarray(p)
    for lo in np.linspace(0, 0.8, 5):
        hi = lo+0.2
        mask = (p >= lo) & (p < hi if hi < 0.999 else p <= 1)
        result.append({"lower":float(lo), "upper":float(hi), "n":int(mask.sum()),
                       "mean_prediction":float(p[mask].mean()) if mask.any() else None,
                       "risk_rate":float(y[mask].mean()) if mask.any() else None})
    return result
