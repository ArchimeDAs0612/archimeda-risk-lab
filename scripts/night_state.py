"""Small file checkpoint helper; no scheduler, process launcher, or auto-restart."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _replace(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(path, state):
    """Atomic main file and previous readable snapshot; never reset run identity/time."""
    path = Path(path)
    if path.exists():
        old_text = path.read_text(encoding='utf-8')
        old = json.loads(old_text)  # Corruption is an error, not permission to erase history.
        for key in ('run_id', 'started_at', 'deadline_at'):
            if old[key] != state[key]:
                raise ValueError('immutable run field changed: ' + key)
        _replace(path.with_suffix('.previous.json'), old_text)
    _replace(path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def next_action(path, workspace, now=None):
    """Read-only recovery decision. Active/uncertain jobs require inspection, never relaunch."""
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    now = now or datetime.now(timezone.utc)
    if Path(state['workspace']).resolve() != Path(workspace).resolve():
        raise ValueError('workspace mismatch')
    if state.get('stop_marker') or state['status'] in ('DONE', 'PAUSED', 'WAITING_HUMAN'):
        return {'action': 'STOP', 'reason': state['status']}
    if now >= datetime.fromisoformat(state['deadline_at']):
        return {'action': 'STOP', 'reason': 'deadline'}
    if state.get('active_jobs'):
        return {'action': 'INSPECT_SAVED_JOBS', 'jobs': state['active_jobs']}
    completed = {x['id'] for x in state['items'] if x['status'] == 'DONE'}
    for item in state['items']:
        if item['status'] in ('RUNNING', 'READY_TO_RESUME') and set(item['depends_on']) <= completed:
            return {'action': 'RESUME', 'item': item['id'], 'next': item['next_action']}
    return {'action': 'NO_READY_ITEM', 'reason': 'inspect blockers; do not rerun completed items'}
