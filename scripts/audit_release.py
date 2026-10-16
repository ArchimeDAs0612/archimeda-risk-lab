"""Bounded release scan: findings and unreviewed binaries are different evidence.

Exit 1 means a blocking finding. Exit 0 only means no blocking findings: callers
must also inspect ``release_ready`` before publishing. Binary provenance can be
attested with --binary-review JSON; a matching hash never proves confidentiality.
No matching credential, path value, or binary contents are printed.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "__pycache__", "runs", ".lab-run", "build", "dist", "node_modules"}
PATTERNS = {
    "personal_absolute_path": r"(?:/Users|/home)/[^\s\"<>]+",
    "temporary_absolute_path": r"(?:/private/tmp|/tmp|/private/var/folders)/[^\s\"<>]+",
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
    "recognizable_token": r"(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "internal_link": r"https?://[^\s/\"<>?#:]+\.(?:internal|corp)(?::[0-9]+)?(?=[/\s\"<>?#]|$)",
    "credential_assignment": r"\b(?:[A-Za-z0-9]+_)*(?:password|passwd|api[_-]?key|access[_-]?token|secret[_-]?key)[\"']?\s*[:=]\s*[\"']?[^\s\"'<>${};,]{4,}",
}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pdf", ".woff", ".woff2", ".ico", ".sqlite", ".db"}


def scan_text(text, file):
    """Return labels only; never retain the potentially sensitive match value."""
    return [{"file": file, "reason": label} for label, pattern in PATTERNS.items()
            if re.search(pattern, text, re.IGNORECASE)]


def _run_git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout


def _review_binary(blob, file, reviews):
    digest = hashlib.sha256(blob).hexdigest()
    claim = reviews.get(file)
    valid = (isinstance(claim, dict) and claim.get("sha256") == digest
             and isinstance(claim.get("provenance"), str) and bool(claim["provenance"].strip())
             and isinstance(claim.get("reviewer"), str) and bool(claim["reviewer"].strip()))
    # Do not echo the claim: user-entered provenance may itself contain secrets.
    return {"file": file, "sha256": digest, "bytes": len(blob),
            "status": "REVIEWED_HASH_MATCH" if valid else "MANUAL_PROVENANCE_REVIEW_REQUIRED"}


def audit(root=ROOT, reviews=None, base=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("audit root must be an existing directory")
    reviews = {} if reviews is None else reviews
    if not isinstance(reviews, dict):
        raise ValueError("binary review files must be an object")
    findings, binary_reviews, count = [], [], 0

    def inspect(blob, file):
        suffix = Path(file).suffix.lower()
        if suffix in BINARY_SUFFIXES or b"\x00" in blob:
            binary_reviews.append(_review_binary(blob, file, reviews))
            return
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            binary_reviews.append(_review_binary(blob, file, reviews))
            return
        findings.extend(scan_text(text, file))

    base_sha = None
    if base is not None:
        # A caller must identify a previously reviewed ancestor. Never silently
        # treat a missing/divergent baseline as an accepted historical audit.
        base_sha = _run_git(root, "rev-parse", "--verify", base + "^{commit}").decode("ascii").strip()
        _run_git(root, "merge-base", "--is-ancestor", base_sha, "HEAD")
        names = _run_git(root, "diff", "--name-only", "-z", base_sha, "--").split(b"\x00")
        paths = sorted(root / name.decode("utf-8") for name in names if name)
    else:
        paths = sorted(root.rglob("*"))
    for path in paths:
        relative = path.relative_to(root)
        # Incremental tracked files never get private-directory exclusions:
        # accidentally adding private state to Git must block publication.
        if base_sha is None and any(p in EXCLUDED or p.endswith(".egg-info") for p in relative.parts):
            continue
        if path.is_symlink():
            findings.append({"file": relative.as_posix(), "reason": "symlink_requires_removal"})
            continue
        if not path.is_file():
            continue
        count += 1
        inspect(path.read_bytes(), relative.as_posix())

    git_scope = "no Git history in this standalone directory"
    commits_checked = 0
    if (root / ".git").exists():
        # --all includes each reachable branch/tag commit, including deleted files.
        # -z handles names containing whitespace/newlines; mode 120000 is a symlink.
        commits = _run_git(root, "rev-list", "HEAD", "^" + base_sha).decode("ascii").splitlines() if base_sha else _run_git(root, "rev-list", "--all").decode("ascii").splitlines()
        for commit in commits:
            changed = None
            if base_sha:
                # -m includes merge-parent changes. Inspect each intermediate
                # tree, so secrets removed in a later commit are still caught.
                changed = set(_run_git(root, "diff-tree", "--root", "-m", "--no-commit-id", "--name-only", "-r", "-z", commit).split(b"\x00"))
            for entry in _run_git(root, "ls-tree", "-rz", commit).split(b"\x00"):
                if not entry:
                    continue
                head, raw_name = entry.split(b"\t", 1)
                if changed is not None and raw_name not in changed:
                    continue
                mode, kind, object_id = head.decode("ascii").split()
                name = raw_name.decode("utf-8", errors="replace")
                label = f"history:{commit}:{name}"
                if mode == "120000":
                    findings.append({"file": label, "reason": "symlink_requires_removal"})
                elif kind != "blob":
                    findings.append({"file": label, "reason": "unreviewed_git_external_object"})
                else:
                    inspect(_run_git(root, "cat-file", "blob", object_id), label)
        commits_checked = len(commits)
        git_scope = (f"{commits_checked} commits after reviewed ancestor {base_sha}; changed objects in each commit scanned; other branches excluded" if base_sha else f"{commits_checked} reachable commits scanned; unreferenced objects/reflogs not audited")
    pending = [x for x in binary_reviews if x["status"] != "REVIEWED_HASH_MATCH"]
    return {"files_checked": count, "findings": findings, "git_scope": git_scope,
            "mode": "incremental" if base_sha else "full", "reviewed_base": base_sha,
            "git_commits_checked": commits_checked, "binary_reviews": binary_reviews,
            "binary_review_required": pending,
            "release_ready": not findings and not pending,
            "status": "BLOCKED" if findings else "MANUAL_REVIEW_REQUIRED" if pending else "SCAN_CLEAR",
            "scope": ("changed tracked worktree files and each new commit after caller-supplied reviewed ancestor; untracked files, other branches and pre-baseline history not re-audited" if base_sha else "heuristic current-tree scan excluding private/generated local directories; all reachable Git commit trees scanned without those exclusions") + "; binary hash/provenance claims only; not an exhaustive security, authorship or licensing proof"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="source or clean release candidate directory")
    parser.add_argument("--binary-review", type=Path, help='JSON {"files": {relative-path: {sha256, provenance, reviewer}}}; history keys use history:<full-commit>:<path>')
    parser.add_argument("--base", help="previously reviewed ancestor; inspect tracked changes and all new intermediate commits only")
    args = parser.parse_args(argv)
    try:
        review = json.loads(args.binary_review.read_text(encoding="utf-8")) if args.binary_review else {}
        if not isinstance(review, dict):
            raise ValueError("binary review document must be an object")
        receipt = audit(args.root, review.get("files", {}), args.base)
    except (OSError, ValueError, subprocess.CalledProcessError):
        # Errors may contain command arguments or paths; emit no raw exception.
        print(json.dumps({"status": "AUDIT_FAILED", "release_ready": False,
                          "findings": [{"file": "audit", "reason": "input_or_git_read_failed"}]}))
        return 1
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if receipt["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
