import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, evaluate, load_scenarios, markdown, read_data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline defensive infrastructure response benchmark")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--scenarios", help="Custom directory of scenario YAML files")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List available scenarios")
    sub.add_parser("validate", help="Validate schema and reference response consistency")
    export = sub.add_parser("export", help="Export agent prompts without checks or reference answers")
    export.add_argument("--output", required=True, type=Path)
    run = sub.add_parser("evaluate", help="Score structured JSON/YAML responses")
    run.add_argument("responses", type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--min-score", type=float, default=0)
    args = parser.parse_args(argv)
    try:
        scenarios = load_scenarios(args.scenarios)
        if args.command == "list":
            for s in scenarios:
                print(f"{s['id']}\t{s['category']}\t{s['title']}")
        elif args.command == "validate":
            reference = {"schema_version": 1, "agent": "reference", "responses": [
                {"scenario_id": s["id"], **s["reference_response"]} for s in scenarios]}
            report = evaluate(scenarios, reference)
            if report["score"] != 100:
                raise InputError("Reference responses do not satisfy every rubric check")
            print(f"Validated {len(scenarios)} scenarios and reference responses")
        elif args.command == "export":
            public = [{k: v for k, v in s.items() if k not in ("checks", "reference_response")}
                      for s in scenarios]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"schema_version": 1, "scenarios": public}, indent=2)+"\n")
            print(args.output)
        else:
            if not 0 <= args.min_score <= 100:
                raise InputError("--min-score must be between 0 and 100")
            report = evaluate(scenarios, read_data(args.responses))
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
            (args.output / "report.md").write_text(markdown(report))
            print(f"Score: {report['score']}/100; reports: {args.output}")
            return 0 if report["score"] >= args.min_score else 1
        return 0
    except (InputError, OSError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
