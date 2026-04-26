"""
Experiment execution: smoke test and scaled training runs.

The smoke test validates basic correctness (completes, loss is finite).
The scaled run executes the full experiment with a wall-clock budget.
All execution goes through sandbox.py — this module never calls subprocess directly.
"""

import os
import re
import math
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sandbox import SandboxResult, run as sandbox_run

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    success: bool
    output: str
    duration_secs: float
    error: Optional[str] = None
    timed_out: bool = False
    output_log: Optional[str] = None  # path to log file for scaled runs
    run_dir: Optional[str] = None


def _build_command(
    venv_path: str,
    train_script: str,
    args: dict,
) -> list[str]:
    """Build the python command from script path and argument dict."""
    python_bin = os.path.join(venv_path, "bin", "python")
    cmd = [python_bin, train_script]
    for key, value in args.items():
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{key}")
        elif value is not None:
            cmd.extend([f"--{key}", str(value)])
    return cmd


def _extract_loss_values(output: str) -> list[float]:
    """Extract all loss values from training output."""
    patterns = [
        r"loss[:\s=]+([0-9eE\+\-\.]+)",
        r"'loss'[:\s]+([0-9eE\+\-\.]+)",
        r'"loss"[:\s]+([0-9eE\+\-\.]+)',
        r"train_loss[:\s=]+([0-9eE\+\-\.]+)",
        r"training_loss[:\s=]+([0-9eE\+\-\.]+)",
    ]
    values = []
    for pattern in patterns:
        for match in re.finditer(pattern, output, re.IGNORECASE):
            try:
                val = float(match.group(1))
                values.append(val)
            except (ValueError, OverflowError):
                continue
    return values


def _check_loss_sanity(loss_values: list[float]) -> tuple[bool, Optional[str]]:
    """
    Validate that loss values are sane: finite and non-NaN.

    Does NOT require decreasing loss (too strict for RL/GANs).
    Logs a warning if loss doesn't decrease but does not fail.
    """
    if not loss_values:
        return False, "No loss values found in output"

    for i, val in enumerate(loss_values):
        if math.isnan(val):
            return False, f"NaN loss detected at step index {i}: {val}"
        if math.isinf(val):
            return False, f"Infinite loss detected at step index {i}: {val}"

    # Warn (but don't fail) if loss doesn't decrease
    if len(loss_values) >= 2:
        first_half = loss_values[: len(loss_values) // 2]
        second_half = loss_values[len(loss_values) // 2 :]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        if avg_second >= avg_first:
            logger.warning(
                "Loss did not decrease during smoke test "
                "(avg first half: %.4f, avg second half: %.4f). "
                "This is a warning only — not failing for RL/GAN compatibility.",
                avg_first, avg_second,
            )

    return True, None


def _check_output_shapes(output: str, expected_shapes: Optional[dict]) -> tuple[bool, Optional[str]]:
    """
    Validate tensor output shapes if the plan specifies expected shapes.

    Searches for common shape reporting patterns in the logs.
    """
    if not expected_shapes:
        return True, None  # no shape check requested

    for name, expected in expected_shapes.items():
        # Look for patterns like "output shape: (32, 10)" or "shape=(32, 10)"
        pattern = rf"{re.escape(name)}.*?(?:shape[:\s=]*)?(\([0-9,\s]+\)|\[[0-9,\s]+\])"
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            found_shape = match.group(1)
            # Normalize to tuple string for comparison
            found_norm = found_shape.replace("[", "(").replace("]", ")").replace(" ", "")
            expected_norm = str(tuple(expected)).replace(" ", "")
            if found_norm != expected_norm:
                return False, (
                    f"Shape mismatch for '{name}': "
                    f"expected {expected_norm}, got {found_norm}"
                )
        else:
            logger.info(
                "Could not find shape for '%s' in output — skipping shape check for this tensor",
                name,
            )

    return True, None


def smoke_test(
    paper_dir: str,
    repo_dir: str,
    venv_path: str,
    plan: dict,
    timeout: int = 120,
) -> RunResult:
    """
    Run a smoke test: quick validation that training starts and loss is sane.

    Criteria for success:
    - Completes without error
    - Finishes within timeout (default 120s)
    - Loss values in output are finite (not NaN/inf)
    - If plan specifies expected_output_shapes, those match

    Does NOT require loss to decrease (RL/GANs may not).
    """
    smoke_config = dict(plan.get("smoke_config", {}))
    train_script = plan["train_script"]

    # Remove non-training keys from smoke_config before merging
    for meta_key in ("timeout_seconds", "description", "success_criteria"):
        smoke_config.pop(meta_key, None)

    # Smoke args override: typically fewer steps, smaller batch
    smoke_args = dict(plan.get("train_args", {}))
    smoke_args.update(smoke_config)

    cmd = _build_command(venv_path, train_script, smoke_args)
    logger.info("Smoke test command: %s", " ".join(cmd))

    result: SandboxResult = sandbox_run(
        command=cmd,
        cwd=repo_dir,
        venv_path=venv_path,
        paper_dir=paper_dir,
        repo_dir=repo_dir,
        timeout_secs=timeout,
    )

    combined_output = result.stdout + "\n" + result.stderr

    # Check 1: Did it complete?
    if result.timed_out:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=f"Smoke test timed out after {timeout}s",
            timed_out=True,
        )

    if result.exit_code != 0:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=(
                f"Smoke test failed (exit {result.exit_code}). "
                f"Stderr tail: {result.stderr[-500:]}"
            ),
        )

    # Check 2: Loss sanity
    loss_values = _extract_loss_values(combined_output)
    loss_ok, loss_error = _check_loss_sanity(loss_values)
    if not loss_ok:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=f"Smoke test loss check failed: {loss_error}",
        )

    # Check 3: Output shapes (if specified)
    expected_shapes = plan.get("expected_output_shapes")
    shapes_ok, shapes_error = _check_output_shapes(combined_output, expected_shapes)
    if not shapes_ok:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=f"Smoke test shape check failed: {shapes_error}",
        )

    logger.info(
        "Smoke test passed in %.1fs — %d loss values extracted, all finite",
        result.duration_secs, len(loss_values),
    )
    return RunResult(
        success=True,
        output=combined_output,
        duration_secs=result.duration_secs,
    )


def scaled_run(
    paper_dir: str,
    repo_dir: str,
    venv_path: str,
    plan: dict,
    overrides: Optional[dict],
    budget_secs: int = 7200,
) -> RunResult:
    """
    Execute the full scaled training run with a wall-clock budget.

    Creates a timestamped run directory, streams output to a log file,
    and enforces the wall-clock budget via sandbox timeout.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = os.path.join(paper_dir, "runs")
    run_dir = os.path.join(runs_dir, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    output_log_path = os.path.join(run_dir, "output.log")

    # Build the training command
    train_script = plan["train_script"]
    train_args = dict(plan.get("train_args", {}))

    # Merge scaled_config from plan
    scaled_config = dict(plan.get("scaled_config", {}))
    train_args.update(scaled_config)

    # Apply overrides last (highest priority)
    if overrides:
        train_args.update(overrides)

    cmd = _build_command(venv_path, train_script, train_args)
    logger.info("Scaled run command: %s", " ".join(cmd))
    logger.info("Run directory: %s", run_dir)
    logger.info("Wall-clock budget: %ds", budget_secs)

    result: SandboxResult = sandbox_run(
        command=cmd,
        cwd=repo_dir,
        venv_path=venv_path,
        paper_dir=paper_dir,
        repo_dir=repo_dir,
        timeout_secs=budget_secs,
    )

    # Write output to log file
    combined_output = result.stdout + "\n" + result.stderr
    try:
        with open(output_log_path, "w") as f:
            f.write(combined_output)
        logger.info("Output written to %s", output_log_path)
    except OSError as exc:
        logger.error("Failed to write output log: %s", exc)

    if result.timed_out:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=f"Scaled run timed out after {budget_secs}s wall-clock budget",
            timed_out=True,
            output_log=output_log_path,
            run_dir=run_dir,
        )

    if result.exit_code != 0:
        return RunResult(
            success=False,
            output=combined_output,
            duration_secs=result.duration_secs,
            error=(
                f"Scaled run failed (exit {result.exit_code}). "
                f"Stderr tail: {result.stderr[-1000:]}"
            ),
            output_log=output_log_path,
            run_dir=run_dir,
        )

    logger.info("Scaled run completed in %.1fs", result.duration_secs)
    return RunResult(
        success=True,
        output=combined_output,
        duration_secs=result.duration_secs,
        output_log=output_log_path,
        run_dir=run_dir,
    )
