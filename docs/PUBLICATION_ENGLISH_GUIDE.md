# Archimeda Risk Lab: English interface and verification guide

This independently implemented research software uses synthetic payment events.
Its results are reproducible examples, not measured production or causal gains.
English bug reports and contributions are welcome through GitHub Issues and PRs.
The [contribution process](../CONTRIBUTING.md) and [security policy](../SECURITY.md)
apply equally to English and Chinese submissions.

## Installation and supported interface

Use CPython 3.9–3.12 in a virtual environment. The measured local baseline is
macOS arm64 Python 3.9; GitHub checks Linux Python 3.9 and 3.11. Other platforms
must be tested separately. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install .
python -m risklab --help
python -m pip install -r requirements-quality.txt
python -W error -m unittest discover -s tests -v
```

The public user interface is the `risklab` command (also `python -m risklab`).
Python functions are inspectable research implementations, not a promised stable
third-party SDK. No authenticated network API or hosted model service is offered.

| Command | Input | Output / behavior |
| --- | --- | --- |
| `generate --out runs/data` | Default independent synthetic configuration; optional `--config` JSON | Synthetic events, labels and field metadata |
| `run --data runs/data --out runs/base` | Generated legacy dataset and registry | Baseline models, metrics and report; rejects invalid field contracts |
| `demo --out runs/demo` | Default configuration | Legacy end-to-end synthetic demonstration |
| `research-demo --out runs/research` | Three preregistered seeds | Separate research runs, frozen candidates, JSON models and seed summary |
| `research --data DATA --out OUT` | Compatible generated dataset | Data engineering, comparable models and complete-path replay |
| `label-study --data runs/research/normal --out runs/labels` | Saved research data/models | Selective-label observed metrics and identification bounds |
| `field-workflow --data runs/research/normal --out runs/tools` | Saved data and field assets | Deterministic tool transcript, failures, recovery and evaluation |
| `field-inventory --metadata META --data EVENTS --out OUT` | Metadata JSON and sample CSV | Physical/logical field inventory and quality evidence |
| `field-change --registry REGISTRY --proposal PROPOSAL --data CSV --out OUT` | Accepted registry and proposed registry | Versioned changes, conflicts and invalidated downstream evidence |
| `field-review --registry REGISTRY --field FIELD --decision approve --reviewer NAME --data CSV --out OUT` | Pending field definition and explicit human decision | Audit record; reviewer text is not authenticated identity |
| `predict --model MODEL --data CSV --out OUT` | This Lab's JSON LR/CART/forest model and compatible samples | Saved probabilities; not arbitrary pickle execution |

Use a new empty output directory for each run. Configuration/CSV/JSON schema
requirements and error behavior are implemented in [contracts](../risklab/contracts.py),
[CLI](../risklab/cli.py), [saved model validation](../risklab/model_artifact.py), and
[field governance](../risklab/field_intelligence.py). Tests exercise time leakage,
missing timestamps, non-finite values, incompatible artifacts and blocked fields.
Review the specific command's contract before passing
external inputs; this is not a general untrusted-data sandbox.

## Actual research evidence and limits

The saved study compares LR, CART and matched-capacity forests across input sets,
with separate train, selection and final time windows. Raw forest final AP is
0.2044 versus score-only LR 0.1298 in the main synthetic run. These are synthetic
ranking metrics, not real fraud-loss reductions. Extra field families have a
negative-gain example, and candidate rediscovery is unstable. Full paths, replay,
counterevidence and a failed independent-seed candidate are retained.

See [results](RC1_RESULTS.md), [methods](RC1_METHODS.md), [reproduction](RC1_REPRODUCTION.json)
and [five-minute interview route](INTERVIEW_GUIDE.md). The online Demo is static
browser exploration of saved results; it does not train models or call an LLM.
Field tools are deterministic, not an LLM Agent. Independent human mastery,
external-domain validity and production consequences remain separate questions.

## Coverage and security checks

```sh
python -m pip install -r requirements-quality.txt
python -W error -m coverage run -m unittest discover -s tests -v
python -m coverage json
python -m coverage xml
python -m coverage html
python -m bandit -r risklab scripts -f json -o runs/quality/bandit.json --exit-zero
python scripts/quality_evidence.py
```

Coverage includes every Python package module, including unexecuted CLI paths.
Bandit scans all Python application and delivery sources. It does not scan JS/SQL
or prove absence of vulnerabilities. The report retains LOW subprocess findings
with file-digest-bound reviews; new, changed or more severe findings block the
gate. A passing local check does not imply a Sonar result, Codecov report, DOI,
or OpenSSF Passing badge. Those require their own public platform evidence.

The fixed verification versions retain Python 3.9 compatibility. They are
development tools, not runtime dependencies; their licenses are recorded in
[verification tool licenses](PUBLICATION_TOOL_LICENSES.txt).

## Citation and archive

[CITATION.cff](../CITATION.cff) identifies the public author handle without
inventing an affiliation or ORCID. Cite the exact commit or actual archived
version. No DOI may be displayed until Zenodo has published the record.
