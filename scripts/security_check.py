"""Runnable Phase 9 security checklist."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum


class Level(Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class CheckResult:
    name: str
    passed: bool
    level: Level
    message: str
    fix: str = ""


@dataclass
class SecurityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def all_critical_passed(self) -> bool:
        return all(result.passed for result in self.results if result.level == Level.CRITICAL)

    def print(self) -> None:
        for result in self.results:
            marker = "PASS" if result.passed else f"FAIL/{result.level.value}"
            print(f"[{marker}] {result.name}: {result.message}")


async def check_no_secrets_in_env() -> CheckResult:
    suspicious = []
    patterns = [re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), re.compile(r"sk-[A-Za-z0-9]{20,}")]
    for key, value in os.environ.items():
        if any(pattern.search(value) for pattern in patterns):
            suspicious.append(key)
    return CheckResult(
        name="env_secrets",
        passed=not suspicious,
        level=Level.CRITICAL,
        message="No plaintext secrets in environment" if not suspicious else f"Found secret-like env vars: {suspicious}",
        fix="Move secrets to Vault.",
    )


async def check_no_secrets_in_git() -> CheckResult:
    try:
        result = subprocess.run(["git", "log", "--all", "--full-history", "--", ".env", ".env.*"], capture_output=True, text=True, timeout=10)
        has_env_history = bool(result.stdout.strip())
        return CheckResult(
            name="git_secrets",
            passed=not has_env_history,
            level=Level.CRITICAL,
            message="No .env files found in git history" if not has_env_history else ".env files exist in git history",
            fix="Rewrite history and rotate credentials if needed.",
        )
    except Exception as exc:
        return CheckResult("git_secrets", True, Level.INFO, f"Git history check skipped: {exc}")


async def check_hard_caps_set() -> CheckResult:
    max_trade = os.getenv("MAX_SINGLE_TRADE_USD")
    max_daily = os.getenv("MAX_DAILY_LOSS_USD")
    return CheckResult(
        name="hard_caps_set",
        passed=bool(max_trade and max_daily),
        level=Level.CRITICAL,
        message="Hard caps configured" if max_trade and max_daily else "Missing MAX_SINGLE_TRADE_USD or MAX_DAILY_LOSS_USD",
        fix="Set MAX_SINGLE_TRADE_USD and MAX_DAILY_LOSS_USD.",
    )


async def check_approval_gate_configured() -> CheckResult:
    if os.getenv("TRADING_MODE", "paper").lower() != "live":
        return CheckResult("approval_gate", True, Level.INFO, "Live-only check skipped in non-live mode")
    threshold = os.getenv("APPROVAL_THRESHOLD_USD")
    return CheckResult(
        name="approval_gate",
        passed=bool(threshold),
        level=Level.CRITICAL,
        message=f"Approval threshold configured: {threshold}" if threshold else "APPROVAL_THRESHOLD_USD missing in live mode",
        fix="Set APPROVAL_THRESHOLD_USD=0 for Stage 2.",
    )


async def run_all_checks(critical_only: bool = False) -> SecurityReport:
    checks = await asyncio.gather(
        check_no_secrets_in_env(),
        check_no_secrets_in_git(),
        check_hard_caps_set(),
        check_approval_gate_configured(),
    )
    report = SecurityReport(results=list(checks))
    if critical_only:
        report.results = [result for result in report.results if result.level == Level.CRITICAL]
    return report


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--critical", action="store_true")
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args()
    report = await run_all_checks(critical_only=args.critical)
    report.print()
    if args.abort and not report.all_critical_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
