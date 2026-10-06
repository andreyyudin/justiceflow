import asyncio
import json
import os

from app.model_evaluation import ModelEvaluationReport, evaluate_model_scenarios
from app.triage import OllamaClient
from evals.model_scenarios import MODEL_SCENARIOS

ReportPayload = dict[str, object]


def report_payload(report: ModelEvaluationReport) -> ReportPayload:
    return {
        "model": report.model,
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "results": [
            {
                "scenario": result.scenario,
                "passed": result.passed,
                "final_priority": result.final_priority,
                "schema_valid": result.schema_valid,
                "evidence_grounded": result.evidence_grounded,
                "rationale_safe": result.rationale_safe,
                "latency_ms": result.latency_ms,
                "failures": result.failures,
            }
            for result in report.results
        ],
    }


async def run() -> ModelEvaluationReport:
    client = OllamaClient(
        base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen3:4b"),
        timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
    )
    return await evaluate_model_scenarios(client, MODEL_SCENARIOS)


def main() -> int:
    report = asyncio.run(run())
    print(json.dumps(report_payload(report), indent=2))
    return 0 if report.total > 0 and report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
