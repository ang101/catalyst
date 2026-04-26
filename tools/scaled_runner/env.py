"""
Virtual environment creation and dependency installation via uv.

Creates isolated Python environments for each paper reproduction,
installs dependencies from the cloned repository, and returns
structured results for the orchestration pipeline.
"""

import os
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

UV_BINARY = "uv"


@dataclass
class EnvResult:
    success: bool
    venv_path: str
    error: Optional[str] = None
    install_stdout: str = ""
    install_stderr: str = ""


def _run_uv(args: list[str], cwd: str, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a uv command, returning the CompletedProcess."""
    cmd = [UV_BINARY] + args
    logger.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max for installs
        env=env,
    )


def _detect_dependency_source(repo_dir: str) -> tuple[str, str]:
    """
    Detect how to install dependencies from the repo.

    Returns (method, path) where method is one of:
    - "requirements": install from requirements.txt
    - "pyproject": install from pyproject.toml (pip install .)
    - "setup_py": install from setup.py (pip install .)
    - "none": no dependency file found
    """
    requirements_txt = os.path.join(repo_dir, "requirements.txt")
    pyproject_toml = os.path.join(repo_dir, "pyproject.toml")
    setup_py = os.path.join(repo_dir, "setup.py")
    setup_cfg = os.path.join(repo_dir, "setup.cfg")

    # Prefer requirements.txt — most explicit
    if os.path.isfile(requirements_txt):
        return ("requirements", requirements_txt)

    # Then pyproject.toml
    if os.path.isfile(pyproject_toml):
        return ("pyproject", repo_dir)

    # Then setup.py / setup.cfg
    if os.path.isfile(setup_py) or os.path.isfile(setup_cfg):
        return ("setup_py", repo_dir)

    return ("none", "")


def setup(paper_dir: str, repo_dir: str) -> EnvResult:
    """
    Create a virtual environment and install dependencies for a paper.

    Steps:
    1. Create papers/<id>/env/ via `uv venv`
    2. Detect dependency source in the cloned repo
    3. Install dependencies via `uv pip install`
    4. Return structured result (no retries — the SOP debug loop handles that)

    Args:
        paper_dir: Path to papers/<id>/ directory
        repo_dir: Path to the cloned repository

    Returns:
        EnvResult with success status, venv path, and any error details
    """
    venv_path = os.path.join(paper_dir, "env")

    # Step 1: Create the virtual environment
    logger.info("Creating virtual environment at %s", venv_path)
    try:
        result = _run_uv(["venv", venv_path, "--python", "3.11", "--clear"], cwd=paper_dir)
    except FileNotFoundError:
        return EnvResult(
            success=False,
            venv_path=venv_path,
            error=f"uv binary not found. Ensure '{UV_BINARY}' is on PATH.",
        )
    except subprocess.TimeoutExpired:
        return EnvResult(
            success=False,
            venv_path=venv_path,
            error="uv venv creation timed out after 600 seconds.",
        )

    if result.returncode != 0:
        return EnvResult(
            success=False,
            venv_path=venv_path,
            error=f"uv venv failed (exit {result.returncode}): {result.stderr.strip()}",
            install_stderr=result.stderr,
        )

    # Step 2: Detect dependency source
    method, dep_path = _detect_dependency_source(repo_dir)
    logger.info("Dependency source: method=%s, path=%s", method, dep_path)

    if method == "none":
        logger.warning("No dependency file found in %s — skipping install", repo_dir)
        return EnvResult(
            success=True,
            venv_path=venv_path,
            error=None,
        )

    # Step 3: Install dependencies
    # uv pip install needs to know which venv to target
    pip_env = os.environ.copy()
    pip_env["VIRTUAL_ENV"] = venv_path

    try:
        if method == "requirements":
            install_result = _run_uv(
                ["pip", "install", "-r", dep_path],
                cwd=repo_dir,
                env=pip_env,
            )
        else:
            # pyproject or setup.py — install the package itself
            install_result = _run_uv(
                ["pip", "install", "."],
                cwd=repo_dir,
                env=pip_env,
            )
    except subprocess.TimeoutExpired:
        return EnvResult(
            success=False,
            venv_path=venv_path,
            error="Dependency installation timed out after 600 seconds.",
        )

    if install_result.returncode != 0:
        return EnvResult(
            success=False,
            venv_path=venv_path,
            error=(
                f"Dependency install failed (exit {install_result.returncode}). "
                f"Method: {method}. Stderr: {install_result.stderr.strip()}"
            ),
            install_stdout=install_result.stdout,
            install_stderr=install_result.stderr,
        )

    logger.info("Dependencies installed successfully into %s", venv_path)
    return EnvResult(
        success=True,
        venv_path=venv_path,
        install_stdout=install_result.stdout,
        install_stderr=install_result.stderr,
    )
