"""Explicit workspace and finite-resource contracts for new research entrypoints."""
from pathlib import Path


def workspace_path(value, workspace=None):
    root = Path.cwd().resolve() if workspace is None else Path(workspace).resolve()
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError('research path escapes the explicitly selected workspace')
    if path == root:
        raise ValueError('research path must name a workspace child')
    return path


def bounded_integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{name} must be an integer in [{lower}, {upper}]')
    return value


def credit_config(config):
    for name, lower, upper in [('bootstrap_repeats', 20, 1000), ('rediscovery_repeats', 1, 30),
                                ('min_leaf', 10, 2000), ('tree_depth', 1, 6), ('candidate_min_select', 10, 2000)]:
        bounded_integer(config[name], name, lower, upper)
    if config['models'] != ['lr', 'forest', 'hist_gradient']:
        raise ValueError('model matrix differs from registered bounded contract')
    if config['inputs'] != ['status_only', 'financial', 'without_status', 'without_bills', 'without_payments']:
        raise ValueError('input matrix differs from registered contract')
    if not isinstance(config['seeds'], list) or not 1 <= len(config['seeds']) <= 5:
        raise ValueError('one to five training seeds required')
    for seed in config['seeds']+[config['primary_seed'], config['split_seed']]:
        bounded_integer(seed, 'seed', 0, 2**32-1)
    if config['primary_seed'] not in config['seeds'] or config['review_fraction'] != .1:
        raise ValueError('invalid primary seed or unregistered review fraction')
    if config['cost_ratios'] != [2, 5, 10]:
        raise ValueError('unregistered cost matrix')


def label_config(config):
    bounded_integer(config['orders'], 'orders', 100, 30000)
    bounded_integer(config['days'], 'days', 30, 365)
    bounded_integer(config['audit_repeats'], 'audit_repeats', 1, 300)
    bounded_integer(config['seed'], 'seed', 0, 2**32-1)
    if not (0 < config['audit_probability'] <= 1 and 0 <= config['delay_min_days'] < config['delay_max_days'] <= 30):
        raise ValueError('invalid observation probabilities or delay bounds')
    times = [0, config['train_end_day'], config['train_asof_day'], config['select_start_day'],
             config['select_end_day'], config['select_asof_day'], config['test_start_day'], config['days'], config['evaluation_asof_day']]
    if not all(type(v) is int for v in times) or times != sorted(times) or times[-1] > 400:
        raise ValueError('unbounded or unordered temporal protocol')
    if config['costs'] != [4, 25, 100] or config['review_fraction'] != .1:
        raise ValueError('unregistered strategy matrix')
