"""Select required research replay; unknown changes fail toward full validation.

This selects expensive integration only, never suppresses behavioral tests,
site/safety checks or a reported failure. The caller supplies an accepted base.
"""
import argparse
import subprocess

# Explicit maintenance exceptions, not a broad scripts/tests exemption.
MAINTENANCE = {
    'AGENTS.md', 'README.md', 'CHECKPOINT.md', 'CHANGELOG.md',
    'demo/index.html', '.github/workflows/check.yml',
    'scripts/audit_release.py', 'scripts/check_scope.py',
    'scripts/prepare_release.py', 'scripts/build_pages.py',
    'scripts/verify_publication.py', 'tests/test_release_scan.py',
    'tests/test_publication.py', 'tests/test_maintenance.py',
}


def requires_research(paths):
    return any(p not in MAINTENANCE and not (p.startswith(('docs/', 'studies/')) and p.endswith('.md')) for p in paths)


def changed_paths(root, base):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    base = git('rev-parse', '--verify', base + '^{commit}').decode('ascii').strip()
    git('merge-base', '--is-ancestor', base, 'HEAD')
    names = set(git('diff', '--name-only', '-z', base, 'HEAD').split(b'\x00'))
    # An intermediate research change reverted at HEAD still needs validation.
    for commit in git('rev-list', 'HEAD', '^' + base).decode('ascii').splitlines():
        names.update(git('diff-tree', '--root', '-m', '--no-commit-id', '--name-only', '-r', '-z', commit).split(b'\x00'))
    return sorted(n.decode('utf-8') for n in names if n)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    try:
        paths = changed_paths('.', args.base)
        print('research=' + str(requires_research(paths)).lower())
        print('baseline=' + args.base)
    except (OSError, ValueError, UnicodeDecodeError, subprocess.CalledProcessError):
        print('research=true')
        print('baseline=')
