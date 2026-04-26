"""
Bubblewrap sandbox wrapper for isolated experiment execution.

All subprocess execution in the scaled_runner goes through this module.
If bwrap is not available, falls back to timeout + ulimit (degraded mode).
"""

import os
import shutil
import subprocess
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_LIMIT_BYTES = 34_359_738_368  # 32 GB virtual address space (PyTorch mmaps extensively)
BWRAP_BINARY = "bwrap"


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_secs: float


@dataclass
class SandboxConfig:
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES
    cpu_time_limit_secs: Optional[int] = None
    extra_ro_binds: list[str] = field(default_factory=list)
    extra_rw_binds: list[str] = field(default_factory=list)


def _bwrap_available() -> bool:
    """Check if bubblewrap is installed and accessible."""
    return shutil.which(BWRAP_BINARY) is not None


def _build_bwrap_command(
    command: list[str],
    cwd: str,
    venv_path: str,
    paper_dir: str,
    repo_dir: str,
    timeout_secs: int,
    config: SandboxConfig,
    env_vars: Optional[dict[str, str]] = None,
) -> list[str]:
    """Build the full bwrap command with all isolation flags."""
    bwrap_args = [
        BWRAP_BINARY,
        "--unshare-all",
        "--cap-drop", "ALL",
        "--die-with-parent",
        # Read-only root filesystem as base
        "--ro-bind", "/", "/",
        # Do NOT expose host /proc — use tmpfs instead
        "--tmpfs", "/proc",
        # Basic device access (null, zero, random, urandom)
        "--dev", "/dev",
        # Writable /tmp (applied before specific binds so it doesn't shadow them)
        "--tmpfs", "/tmp",
        # Writable binds for paper work directories (AFTER tmpfs /tmp so
        # paths under /tmp are re-mounted on top of the tmpfs)
        "--bind", paper_dir, paper_dir,
        "--bind", repo_dir, repo_dir,
        "--bind", venv_path, venv_path,
        # Set working directory
        "--chdir", cwd,
    ]

    # Add any extra read-only binds
    for path in config.extra_ro_binds:
        if os.path.exists(path):
            bwrap_args.extend(["--ro-bind", path, path])

    # Add any extra read-write binds
    for path in config.extra_rw_binds:
        if os.path.exists(path):
            bwrap_args.extend(["--bind", path, path])

    # Set environment variables inside the sandbox
    if env_vars:
        for key, value in env_vars.items():
            bwrap_args.extend(["--setenv", key, value])

    # Ensure venv bin is on PATH inside sandbox
    venv_bin = os.path.join(venv_path, "bin")
    current_path = os.environ.get("PATH", "/usr/bin:/bin")
    bwrap_args.extend(["--setenv", "PATH", f"{venv_bin}:{current_path}"])
    # Disable Python output buffering so logs stream in real-time
    bwrap_args.extend(["--setenv", "PYTHONUNBUFFERED", "1"])

    # Resource limits via prlimit flags (bwrap doesn't support these directly,
    # so we wrap the inner command with prlimit)
    prlimit_args = []
    if config.memory_limit_bytes:
        prlimit_args.append(f"--as={config.memory_limit_bytes}")
    cpu_limit = config.cpu_time_limit_secs or timeout_secs
    if cpu_limit:
        prlimit_args.append(f"--cpu={cpu_limit}")

    # Build the inner command, optionally wrapped with prlimit
    if prlimit_args and shutil.which("prlimit"):
        inner = ["prlimit"] + prlimit_args + ["--"] + command
    else:
        inner = command

    full_cmd = bwrap_args + ["--"] + inner

    # Wrap the entire thing with timeout
    return ["timeout", "--signal=KILL", str(timeout_secs)] + full_cmd


def _build_fallback_command(
    command: list[str],
    cwd: str,
    venv_path: str,
    timeout_secs: int,
    config: SandboxConfig,
) -> list[str]:
    """Build a degraded sandbox command using just timeout + ulimit."""
    # Use bash to set ulimits then exec the command
    venv_bin = os.path.join(venv_path, "bin")
    current_path = os.environ.get("PATH", "/usr/bin:/bin")

    ulimit_stmts = []
    mem_kb = config.memory_limit_bytes // 1024
    ulimit_stmts.append(f"ulimit -v {mem_kb} 2>/dev/null")

    cpu_limit = config.cpu_time_limit_secs or timeout_secs
    if cpu_limit:
        ulimit_stmts.append(f"ulimit -t {cpu_limit} 2>/dev/null")

    cmd_str = " ".join(command)
    ulimit_block = "; ".join(ulimit_stmts)
    bash_script = f'export PATH="{venv_bin}:{current_path}"; {ulimit_block}; exec {cmd_str}'

    return [
        "timeout", "--signal=KILL", str(timeout_secs),
        "bash", "-c", bash_script,
    ]


def run(
    command: list[str],
    cwd: str,
    venv_path: str,
    paper_dir: str,
    repo_dir: str,
    timeout_secs: int,
    env_vars: Optional[dict[str, str]] = None,
    config: Optional[SandboxConfig] = None,
) -> SandboxResult:
    """
    Execute a command inside a sandboxed environment.

    Uses bubblewrap if available, otherwise falls back to timeout + ulimit.
    All experiment execution MUST go through this function.
    """
    if config is None:
        config = SandboxConfig()

    use_bwrap = _bwrap_available()

    if use_bwrap:
        full_cmd = _build_bwrap_command(
            command=command,
            cwd=cwd,
            venv_path=venv_path,
            paper_dir=paper_dir,
            repo_dir=repo_dir,
            timeout_secs=timeout_secs,
            config=config,
            env_vars=env_vars,
        )
    else:
        logger.warning(
            "bwrap not found — running in DEGRADED sandbox mode "
            "(timeout + ulimit only, no filesystem isolation)"
        )
        full_cmd = _build_fallback_command(
            command=command,
            cwd=cwd,
            venv_path=venv_path,
            timeout_secs=timeout_secs,
            config=config,
        )

    logger.info("Sandbox command: %s", " ".join(full_cmd[:10]) + " ...")

    # Merge environment variables for the subprocess
    proc_env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin")
    proc_env["PATH"] = f"{venv_bin}:{proc_env.get('PATH', '')}"
    proc_env["VIRTUAL_ENV"] = venv_path
    proc_env["PYTHONUNBUFFERED"] = "1"
    if env_vars:
        proc_env.update(env_vars)

    start = time.monotonic()
    try:
        result = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_secs + 30,  # grace period beyond the timeout command
            env=proc_env if not use_bwrap else None,  # bwrap manages its own env
        )
        elapsed = time.monotonic() - start

        # exit code 137 = SIGKILL (from timeout --signal=KILL), 124 = timeout default
        timed_out = result.returncode in (-9, 137, 124)

        return SandboxResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=timed_out,
            duration_secs=round(elapsed, 2),
        )

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr="Process exceeded hard timeout (subprocess.TimeoutExpired)",
            timed_out=True,
            duration_secs=round(elapsed, 2),
        )
    except FileNotFoundError as exc:
        elapsed = time.monotonic() - start
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr=f"Command not found: {exc}",
            timed_out=False,
            duration_secs=round(elapsed, 2),
        )
    except OSError as exc:
        elapsed = time.monotonic() - start
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr=f"OS error executing sandbox: {exc}",
            timed_out=False,
            duration_secs=round(elapsed, 2),
        )
