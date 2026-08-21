from __future__ import annotations

import asyncio
from subprocess import PIPE
from typing import Sequence


async def run_command(
    command: Sequence[str], cwd: str | None = None, timeout: float | None = None
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=PIPE,
        stderr=PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    return process.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
