#!/usr/bin/env python3
"""
Run a briefing locally.

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/run_briefing.py
    ANTHROPIC_API_KEY=sk-... python scripts/run_briefing.py claude-code-market-daily
    ANTHROPIC_API_KEY=sk-... python scripts/run_briefing.py developer-market-daily

File-based briefings write to the path in the BriefingConfig (e.g. .claude/rules/).
Email briefings require BRIEFING_RESEND_API_KEY, BRIEFING_FROM_ADDRESS, BRIEFING_EMAIL_TO.

Claude Code loads .claude/rules/ automatically at session start, so running
this script before opening a session gives Claude Code fresh market context.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so briefing_engine and app imports resolve
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

from briefing_engine.runner import run  # noqa: E402


async def main() -> None:
    briefing_id = sys.argv[1] if len(sys.argv) > 1 else "claude-code-market-daily"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Running briefing: {briefing_id}")
    result = await run(
        briefing_id,
        api_key,
        base_dir=str(_PROJECT_ROOT),
        resend_api_key=os.environ.get("BRIEFING_RESEND_API_KEY", ""),
        email_from=os.environ.get("BRIEFING_FROM_ADDRESS", ""),
        email_to=os.environ.get("BRIEFING_EMAIL_TO", ""),
    )

    if result.get("status") == "inactive":
        print(f"Briefing {briefing_id!r} is marked inactive — nothing to do.")
        return

    for path in result.get("channels", []):
        print(f"Delivered → {path}")
    print(f"Done ({result.get('chars', 0):,} chars)")


if __name__ == "__main__":
    asyncio.run(main())
