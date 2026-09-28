# InfraBench v0.1

An offline Python CLI for evaluating structured AI-agent responses to defensive DevOps and cybersecurity incidents. Ten synthetic scenarios span Linux, Docker, networking, security, databases, cloud IAM, and incident response.

**Scope:** v0.1 scores proposed diagnosis and recovery plans using transparent lexical rubrics. It does not run an agent, execute generated commands, provision infrastructure, or prove a remediation works. A high score is evidence of rubric coverage, not operational competence or safety certification.

## Quick start

Requires Python 3.11 or newer.

```sh
python -m venv .venv
. .venv/bin/activate
pip install '.[dev]'
infrabench list
infrabench validate
infrabench export --output prompts.json
infrabench evaluate examples/reference-responses.json --output reports/reference --min-score 100
infrabench evaluate examples/partial-response.json --output reports/partial
pytest -q
```

The reference fixture scores 100 by design. It is a self-consistency check, **not a measured model result**. The partial example illustrates missing coverage and lost credit.

## Evaluate an agent

1. Export prompts. Give the agent each scenario's prompt, context and constraints, without the reference answers or rubric.
2. Collect the agent's response in the JSON structure below. Use `actions` for proposed actions only; put discussion of rejected alternatives in `diagnosis`.
3. Evaluate the saved responses. Review the check-level evidence in `report.json` and the summary in `report.md`.
4. Record model/version, prompt, temperature, date and tool access separately alongside the submission. Compare runs against the same suite hash.

```json
{
  "schema_version": 1,
  "agent": "provider/model-version/run-id",
  "responses": [{
    "scenario_id": "linux-disk-pressure",
    "diagnosis": "Your evidence-based diagnosis",
    "actions": "Your ordered, scoped remediation plan",
    "verification": "How you would verify recovery",
    "rollback": "How you would recover from a failed change"
  }]
}
```

JSON and YAML submissions are supported. Missing scenarios score zero. Unknown or duplicate IDs, unknown fields and invalid types are errors. Empty response fields are permitted and usually lose credit. Input files are limited to 2 MB. Exit codes: `0` success/threshold met, `1` score below `--min-score`, `2` invalid input or I/O failure. `--scenarios DIR` goes before the subcommand.

## Scoring and limitations

Each check has a positive integer weight and one of `contains_all`, `contains_any`, or `excludes_all`. Matching is case-insensitive with whitespace collapsed. A scenario's raw score is earned weight / total weight × 100. Any failed critical check sets its final score to zero. The suite score is the equal-weight mean of scenario scores, including missing scenarios. Bundled scenarios allocate 30/35/20/15 points to diagnosis/actions/verification/rollback plus 10 to a critical forbidden-action check (110 total, normalized to 100).

Reports include check definitions, observed response fields, matched phrases, earned weights, coverage, version and SHA-256 fingerprints of the parsed suite/submission. They are deterministic for identical inputs. Reports may contain response data: keep secrets out of submissions.

Lexical checks can be gamed by copying keywords, miss valid paraphrases, fail to understand negation, and miss unsafe actions outside their short deny lists. The checks are review aids, not a safety boundary. Human reviewers must assess causality, command correctness, sequencing, scope, evidence preservation and recovery. Docker isolates the scorer; it is not an agent sandbox. No model API keys or network calls are required by the scorer.

## Scenarios

| ID | Topic |
|---|---|
| linux-disk-pressure | Deleted open log consuming disk blocks |
| linux-systemd-permissions | File ownership versus systemd sandboxing |
| docker-compose-dns | Container localhost versus service DNS |
| docker-healthcheck | Missing healthcheck dependency |
| network-dns-cache | Cached DNS after a migration |
| security-ssh-hardening | SSH hardening with lockout prevention |
| database-postgres-blocking | Idle transaction blocking DDL |
| database-redis-exposure | Accidental public port exposure |
| cloud-iam-scope | Prefix-scoped S3 read permissions |
| incident-suspected-credential-leak | Token containment and evidence preservation |

## Author a scenario

Copy a bundled YAML file from `src/infrabench/scenarios/` into a custom directory. The machine-readable schema is `src/infrabench/scenario.schema.json`; submissions use `response.schema.json` in the same folder. Required scenario fields: `schema_version`, unique `id`, `title`, `category`, `difficulty`, `prompt`, `context`, `constraints`, `checks`, and `reference_response`.

Each check needs a unique `id`, human-readable `description`, a response `field`, `operator`, nonempty `values`, `weight`, and `critical` flag. Keep evidence synthetic and actions defensive. Add a reference answer, a plausible incorrect answer, and a regression test for any new scoring behavior. Then run:

```sh
infrabench --scenarios ./my-scenarios validate
infrabench --scenarios ./my-scenarios evaluate answers.json --output reports/custom
```

`validate` checks the schema, unique IDs and full reference-answer credit. This is not independent technical validation of a reference solution. Avoid giving the public rubric and reference fixtures to a model during evaluation; use private held-out scenarios for meaningful comparisons.

## Docker

```sh
docker build -t infrabench:0.1 .
docker run --rm --network none infrabench:0.1 validate
mkdir -p reports
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  -v "$PWD/examples:/input:ro" -v "$PWD/reports:/output" \
  infrabench:0.1 evaluate /input/reference-responses.json --output /output --min-score 100
```

The image defaults to a non-root user. The example uses your UID so report files remain writable on Linux. Image building downloads dependencies; runtime scoring needs no network.

## Development and CI

```sh
ruff check .
pytest -q
python -m build
```

GitHub Actions tests Python 3.11–3.14, checks lint, validates the suite, builds distributions, tests installed-wheel resources from outside the checkout, and builds/runs the Docker image. Dependencies use compatible version ranges; builds are not bit-for-bit reproducible. No production hosts, credentials, Docker socket, or cloud accounts are used by the tests.

## Roadmap

Human-scored rubric overlays, calibrated semantic checks, held-out scenarios, and a separately designed disposable execution harness. Keep execution adapters explicitly separate from this data-only scorer.

MIT licensed. AI-assisted implementation; scenario references and heuristic checks should receive independent domain review before use in hiring or model ranking.
