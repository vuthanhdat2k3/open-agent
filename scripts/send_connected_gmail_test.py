"""Docker wrapper for the connected Gmail pipeline test.

Usage:
  python scripts/send_connected_gmail_test.py --scenario customer --send --sync --wait-seconds 30
  python scripts/send_connected_gmail_test.py --scenario all --send --sync --wait-seconds 60

Scenarios: customer, customer_calendar, calendar, normal, spam, all. Without --send the command is a dry-run.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    worktree = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "app.customer_intelligence.test_mail",
        *sys.argv[1:],
    ]
    return subprocess.run(command, cwd=worktree, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
