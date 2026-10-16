"""Validate complete Python scan inputs and publish bounded verification evidence.

No coverage target is invented: all package modules, including uncovered CLI
code, stay in the denominator. Reviewed LOW Bandit findings remain visible;
new findings, changed reviewed files, scan errors and missing files fail closed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from defusedxml import ElementTree as ET


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_xml(raw, coverage):
    # Only our local coverage output is expected; reject entity/DTD declarations.
    # This is not a general remote XML parser or external-user upload endpoint.
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('coverage XML declarations are forbidden')
    tree = ET.fromstring(raw)
    names = [node.attrib['filename'] for node in tree.findall('.//class')]
    if len(names) != len(set(names)) or set(names) != set(coverage['files']):
        raise ValueError('upload XML must preserve every repository-relative package path')
    if int(tree.attrib['lines-valid']) != coverage['totals']['num_statements']:
        raise ValueError('upload XML coverage denominator differs from JSON')


def summarize(root, coverage, bandit, review, commit=None):
    root = Path(root)
    package = {p.relative_to(root).as_posix() for p in (root/'risklab').rglob('*.py')}
    scanned = package | {p.relative_to(root).as_posix() for p in (root/'scripts').rglob('*.py')}
    if not package or set(coverage['files']) != package:
        raise ValueError('coverage must include every package Python module')
    if bandit.get('errors') or set(bandit['metrics']) - {'_totals'} != scanned:
        raise ValueError('security scan errors or incomplete Python source scope')
    totals = coverage['totals']
    statements = totals['num_statements']
    branches = totals['num_branches']
    if statements <= 0 or totals['covered_lines'] + totals['missing_lines'] != statements:
        raise ValueError('invalid coverage totals')
    accepted = {(x['file'], x['test_id'], x['line'], x['sha256']) for x in review['findings']
                if x.get('rationale')}
    findings = []
    for item in bandit['results']:
        name = item['filename'].removeprefix('./')
        if name not in scanned:
            raise ValueError('finding outside declared scan scope')
        key = (name, item['test_id'], item['line_number'], digest(root/name))
        reviewed = item['issue_severity'] == 'LOW' and key in accepted
        findings.append(dict(file=name, line=item['line_number'], test_id=item['test_id'],
                             severity=item['issue_severity'], reviewed=reviewed,
                             message=item['issue_text']))
    return dict(source_commit=commit, coverage_tool=coverage['meta']['version'],
                line_percent=100*totals['covered_lines']/statements,
                branch_percent=100*totals['covered_branches']/branches if branches else None,
                combined_percent=totals['percent_covered'], coverage_totals=totals,
                coverage_scope=sorted(package), security_scope=sorted(scanned),
                source_sha256={name:digest(root/name) for name in sorted(scanned)},
                security_findings=findings, security_gate_passed=all(x['reviewed'] for x in findings),
                limits=['Python only; JS and SQL not covered by Bandit or this coverage report.',
                        'Executed lines/branches do not prove correctness or absence of vulnerabilities.',
                        'LOW finding reviews are Codex-assisted, not independent human certification.',
                        'No Sonar, Codecov, DOI or OpenSSF Passing award is inferred from this report.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--coverage', type=Path, default=Path('runs/quality/coverage.json'))
    parser.add_argument('--bandit', type=Path, default=Path('runs/quality/bandit.json'))
    parser.add_argument('--xml', type=Path, default=Path('runs/quality/coverage.xml'))
    parser.add_argument('--review', type=Path, default=Path('config/security-review.json'))
    parser.add_argument('--out', type=Path, default=Path('runs/quality/summary.json'))
    parser.add_argument('--commit')
    args = parser.parse_args()
    coverage = json.loads(args.coverage.read_text())
    validate_xml(args.xml.read_bytes(), coverage)
    result = summarize(args.root, coverage,
                       json.loads(args.bandit.read_text()), json.loads(args.review.read_text()), args.commit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['line_percent','branch_percent','security_gate_passed']}))
    return 0 if result['security_gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
