import json

from app.evaluation import evaluate_scenarios
from evals.scenarios import SCENARIOS


def main() -> int:
    report = evaluate_scenarios(SCENARIOS)
    output = {
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "results": [
            {
                "scenario": result.scenario,
                "actual": result.actual,
                "expected": result.expected,
                "passed": result.passed,
            }
            for result in report.results
        ],
    }
    print(json.dumps(output, indent=2))
    return 0 if report.total > 0 and report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
