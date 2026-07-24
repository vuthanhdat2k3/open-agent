from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import SessionLocal, init_db
from app.evals.executor import ExecutionOutput, LiveAgentExecutor, RecordedOutputExecutor
from app.evals.quality_gate import quality_gate_passes
from app.services.evaluation_service import EvaluationService


def _recorded_executor(path: Path) -> RecordedOutputExecutor:
    payload = json.loads(path.read_text(encoding="utf-8"))
    outputs = {
        item["case_id"]: ExecutionOutput(
            output=item["output"],
            observed_tools=item.get("observed_tools", []),
            latency_ms=int(item.get("latency_ms", 0)),
            cost_usd=float(item.get("cost_usd", 0.0)),
        )
        for item in payload
    }
    return RecordedOutputExecutor(outputs)


async def _run(args: argparse.Namespace) -> int:
    await init_db()
    executor = (
        _recorded_executor(args.recorded_outputs)
        if args.recorded_outputs
        else LiveAgentExecutor()
    )
    mode = "recorded" if args.recorded_outputs else "live"
    async with SessionLocal() as db:
        service = EvaluationService(db)
        run = await service.create_run(
            args.org,
            args.suite,
            args.release,
            executor,
            execution_mode=mode,
            baseline_run_id=args.baseline,
        )
        comparison = (
            await service.compare_runs(args.org, run.id, args.baseline)
            if args.baseline
            else None
        )
    passed = quality_gate_passes(
        pass_rate=run.pass_rate,
        min_pass_rate=args.min_pass_rate,
        latency_delta=(
            comparison["average_latency_ms_delta"] if comparison else None
        ),
        max_latency_regression_ms=args.max_latency_regression_ms,
        cost_delta=comparison["total_cost_usd_delta"] if comparison else None,
        max_cost_regression_usd=args.max_cost_regression_usd,
    )
    print(
        json.dumps(
            {
                "run_id": run.id,
                "pass_rate": run.pass_rate,
                "passed_cases": run.passed_cases,
                "total_cases": run.total_cases,
                "comparison": comparison,
                "gate": "passed" if passed else "failed",
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an AgentOS evaluation gate")
    parser.add_argument("--org", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--recorded-outputs", type=Path)
    parser.add_argument("--min-pass-rate", type=float, default=0.95)
    parser.add_argument("--max-latency-regression-ms", type=float)
    parser.add_argument("--max-cost-regression-usd", type=float)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())

