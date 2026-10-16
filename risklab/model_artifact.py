"""Inspectable JSON inference for this Lab's binary LR/CART/forest models.

Not a general sklearn interchange format. No pickle, dynamic imports or eval.
The preprocessing and tree input domain remain exactly those used for fitting.
"""
import numpy as np
from scipy.special import expit


def export_model(bundle, threshold):
    prep = bundle['prep']
    model = bundle['model']
    if model.classes_.tolist() != [0, 1]:
        raise ValueError('only binary classes [0,1] supported')
    artifact = dict(format='risklab-inference-v1', kind=bundle['kind'],
                    preprocessing=prep.metadata(), threshold=float(threshold))
    if bundle['kind'] == 'lr':
        artifact.update(coefficients=model.coef_[0].tolist(), intercept=float(model.intercept_[0]),
                        scaler_mean=bundle['scaler'].mean_.tolist(), scaler_scale=bundle['scaler'].scale_.tolist())
    else:
        trees = model.estimators_ if bundle['kind'] == 'forest' else [model]
        artifact['trees'] = [dict(feature=t.tree_.feature.tolist(), threshold=t.tree_.threshold.tolist(),
            left=t.tree_.children_left.tolist(), right=t.tree_.children_right.tolist(),
            # Normalize explicitly; sklearn versions may store counts/proportions.
            probability=(t.tree_.value[:, 0, 1] / t.tree_.value[:, 0, :].sum(axis=1)).tolist()) for t in trees]
    return artifact


def _finite(value, shape):
    array = np.asarray(value, dtype=float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError('invalid finite artifact array')
    return array


def predict_json(artifact, frame):
    if artifact.get('format') != 'risklab-inference-v1':
        raise ValueError('unsupported artifact format')
    prep = artifact['preprocessing']
    columns = prep['input_columns']
    if not columns or len(set(columns)) != len(columns) or prep['dtype'] != 'float32':
        raise ValueError('invalid preprocessing contract')
    if not set(columns) <= set(frame):
        raise ValueError('missing inference columns')
    x = frame[columns].to_numpy(dtype=float)
    if np.isinf(x).any():
        raise ValueError('infinite inference value')
    medians = _finite([prep['train_medians'][c] for c in columns], (len(columns),))
    missing = np.isnan(x)
    x = np.column_stack([np.where(missing, medians, x), missing.astype(float)]).astype(np.float32)
    if not np.isfinite(x).all():
        raise ValueError('inference value overflows float32')
    width = x.shape[1]
    if artifact['kind'] == 'lr':
        mean = _finite(artifact['scaler_mean'], (width,))
        scale = _finite(artifact['scaler_scale'], (width,))
        coefficients = _finite(artifact['coefficients'], (width,))
        if (scale <= 0).any() or not np.isfinite(artifact['intercept']):
            raise ValueError('invalid LR scaler/intercept')
        # StandardScaler preserves float32 and rounds after each in-place op.
        x = x.copy()
        x -= mean
        x /= scale
        return expit(np.sum(x * coefficients, axis=1) + artifact['intercept'])
    if artifact['kind'] not in ('tree', 'forest') or not artifact.get('trees'):
        raise ValueError('invalid model kind/trees')
    predictions = []
    for tree in artifact['trees']:
        n = len(tree['feature'])
        if n == 0:
            raise ValueError('empty tree')
        features = _finite(tree['feature'], (n,))
        thresholds = _finite(tree['threshold'], (n,))
        left = _finite(tree['left'], (n,))
        right = _finite(tree['right'], (n,))
        probs = _finite(tree['probability'], (n,))
        if not np.equal(features, np.floor(features)).all() or not np.equal(left, np.floor(left)).all() or not np.equal(right, np.floor(right)).all():
            raise ValueError('noninteger tree index')
        internal = left != -1
        if ((left == -1) != (right == -1)).any() or (probs < 0).any() or (probs > 1).any():
            raise ValueError('invalid leaf/probability')
        if ((features[internal] < 0) | (features[internal] >= width)).any():
            raise ValueError('invalid feature index')
        if ((left[internal] <= np.flatnonzero(internal)) | (right[internal] <= np.flatnonzero(internal)) | (left[internal] >= n) | (right[internal] >= n)).any():
            raise ValueError('cyclic or invalid child index')
        nodes = np.zeros(len(x), dtype=int)
        for _ in range(n):
            active = np.flatnonzero(left[nodes] != -1)
            if len(active) == 0:
                break
            node = nodes[active]
            f = features[node].astype(int)
            # Cast to float64 explicitly, matching sklearn's double threshold.
            branch = x[active, f].astype(float) <= thresholds[node]
            nodes[active] = np.where(branch, left[node], right[node]).astype(int)
        predictions.append(probs[nodes])
    return np.mean(predictions, axis=0)
