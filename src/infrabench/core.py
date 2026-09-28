"""Data-only loading and deterministic rubric evaluation. No command execution."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from . import __version__

MAX_BYTES = 2_000_000


class InputError(ValueError):
    """Invalid benchmark input."""


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise InputError("Mapping keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_data(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise InputError(f"{path}: input exceeds {MAX_BYTES} bytes")
    try:
        # YAML is a superset of JSON; duplicate keys rejected in either format.
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise InputError(f"{path}: invalid YAML/JSON") from exc


def validate(data, kind):
    schema = json.loads(files("infrabench").joinpath(f"{kind}.schema.json").read_text())
    try:
        errors = list(Draft202012Validator(schema).iter_errors(data))
    except RecursionError as exc:
        raise InputError("Recursive input is not supported") from exc
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.absolute_path)) or "root"
        raise InputError(f"{kind} {location}: {error.message}")


def load_scenarios(directory=None):
    root = Path(directory) if directory else Path(str(files("infrabench").joinpath("scenarios")))
    paths = sorted([*root.glob("*.yaml"), *root.glob("*.yml")])
    if not paths:
        raise InputError(f"No scenarios in {root}")
    scenarios = []
    seen = set()
    for path in paths:
        scenario = read_data(path)
        validate(scenario, "scenario")
        if scenario["id"] in seen:
            raise InputError(f"Duplicate scenario id: {scenario['id']}")
        seen.add(scenario["id"])
        ids = [check["id"] for check in scenario["checks"]]
        if len(ids) != len(set(ids)):
            raise InputError(f"Duplicate check id in {scenario['id']}")
        scenarios.append(scenario)
    return scenarios


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def normalize(text):
    return " ".join(text.casefold().split())


def evaluate(scenarios, submission):
    validate(submission, "response")
    known = {s["id"] for s in scenarios}
    answers = {}
    for answer in submission["responses"]:
        sid = answer["scenario_id"]
        if sid not in known or sid in answers:
            raise InputError(f"Unknown or duplicate response scenario_id: {sid}")
        answers[sid] = answer
    results = []
    for scenario in scenarios:
        answer = answers.get(scenario["id"])
        checks = []
        for check in scenario["checks"]:
            observed = answer[check["field"]] if answer else ""
            haystack = normalize(observed)
            matches = [value for value in check["values"] if normalize(value) in haystack]
            op = check["operator"]
            passed = bool(answer) and (
                (op == "contains_all" and len(matches) == len(check["values"]))
                or (op == "contains_any" and bool(matches))
                or (op == "excludes_all" and not matches)
            )
            checks.append({**check, "passed": passed, "matched": matches,
                           "observed": observed, "earned": check["weight"] if passed else 0})
        total = sum(c["weight"] for c in checks)
        earned = sum(c["earned"] for c in checks)
        critical_failure = any(c["critical"] and not c["passed"] for c in checks)
        raw = 100 * earned / total
        results.append({"id": scenario["id"], "category": scenario["category"],
                        "missing": answer is None, "raw_score": round(raw, 2),
                        "score": 0.0 if critical_failure else round(raw, 2),
                        "critical_failure": critical_failure, "checks": checks})
    return {"report_version": 1, "infrabench_version": __version__,
            "agent": submission["agent"], "suite_sha256": fingerprint(scenarios),
            "submission_sha256": fingerprint(submission),
            "scoring": "Equal-weight scenario mean; critical failure zeros scenario",
            "limitations": "Lexical rubric screening only; human review required. No commands run.",
            "scenario_count": len(results), "answered_count": len(answers),
            "score": round(sum(r["score"] for r in results) / len(results), 2),
            "results": results}


def markdown(report):
    def safe(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ")
    lines = ["# InfraBench report", "", f"Agent: {safe(report['agent'])}", "",
             f"Score: **{report['score']}/100** · Coverage: {report['answered_count']}/{report['scenario_count']}",
             "", report["limitations"], "", "| Scenario | Score | Critical failure | Missing |",
             "|---|---:|---|---|"]
    for result in report["results"]:
        lines.append(f"| {safe(result['id'])} | {result['score']} | {result['critical_failure']} | {result['missing']} |")
    for result in report["results"]:
        lines.extend(["", f"## {safe(result['id'])}", ""])
        for check in result["checks"]:
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {safe(check['id'])}: {safe(check['description'])} ({check['earned']}/{check['weight']})")
    lines.extend(["", f"Suite SHA-256: {report['suite_sha256']}",
                  f"Submission SHA-256: {report['submission_sha256']}"])
    return "\n".join(lines) + "\n"
