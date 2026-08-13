from __future__ import annotations


class JobKey:
    CI_SCHEDULER_TICK = "ci_scheduler_tick"
    CI_RETRY_DUE_CASES = "ci_retry_due_cases"
    CI_DISPATCH_INGESTED = "ci_dispatch_ingested"
    CI_OUTBOX_DISPATCH = "ci_outbox_dispatch"
    AUTO_ROLLBACK_SWEEP = "auto_rollback_sweep"
    FAIL_ORPHANED_CHAT_RUNS = "fail_orphaned_chat_runs"
