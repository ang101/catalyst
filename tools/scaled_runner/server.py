"""
MCP server entry point for the scaled_runner tool.

Orchestrates: env.setup() -> patcher.apply_patches() -> runner.smoke_test()
-> runner.scaled_run() -> metrics.extract()

Supports both MCP server mode and --cli mode for direct invocation.
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

import env
import metrics
import patcher
import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

PAPERS_DIR = os.environ.get(
    "PAPER_REPRO_PAPERS_DIR",
    os.path.expanduser("~/.zeroclaw/workspace/paper-repro/papers"),
)

mcp = FastMCP("scaled_runner")


def _update_status(paper_dir: str, outcome: str, artifacts: list[str], error: Optional[str] = None) -> None:
    """Append an execute phase entry to STATUS.json."""
    status_path = os.path.join(paper_dir, "STATUS.json")
    try:
        if os.path.isfile(status_path):
            with open(status_path, "r") as f:
                status = json.load(f)
        else:
            status = {"phases": []}
    except (json.JSONDecodeError, OSError):
        status = {"phases": []}

    if "phases" not in status:
        status["phases"] = []

    status["phases"].append({
        "phase": "execute",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "artifacts": artifacts,
        "error": error,
    })

    try:
        with open(status_path, "w") as f:
            json.dump(status, f, indent=2)
    except OSError as exc:
        logger.error("Failed to write STATUS.json: %s", exc)


def run_pipeline(
    paper_id: str,
    plan: dict,
    scaled_config_overrides: Optional[dict] = None,
    wall_clock_budget_secs: int = 7200,
    smoke_timeout_secs: int = 120,
) -> dict[str, Any]:
    """
    Execute the full scaled_runner pipeline for a paper.

    Returns a structured result dict with status, metrics, and paths.
    """
    paper_dir = os.path.join(PAPERS_DIR, paper_id)
    repo_dir = os.path.join(paper_dir, "repo")

    if not os.path.isdir(paper_dir):
        return {
            "paper_id": paper_id,
            "status": "failed",
            "metrics": None,
            "log_path": "",
            "run_dir": "",
            "error": f"Paper directory not found: {paper_dir}",
        }

    if not os.path.isdir(repo_dir):
        return {
            "paper_id": paper_id,
            "status": "failed",
            "metrics": None,
            "log_path": "",
            "run_dir": "",
            "error": f"Repository not found at {repo_dir}. Clone it first.",
        }

    # Step 1: Environment setup
    logger.info("Step 1/5: Setting up environment for %s", paper_id)
    env_result = env.setup(paper_dir, repo_dir)
    if not env_result.success:
        _update_status(paper_dir, "failed", [], env_result.error)
        return {
            "paper_id": paper_id,
            "status": "failed",
            "metrics": None,
            "log_path": "",
            "run_dir": "",
            "error": f"Environment setup failed: {env_result.error}",
        }

    # Step 2: Apply patches
    logger.info("Step 2/5: Applying patches for %s", paper_id)
    patch_result = patcher.apply_patches(paper_dir, repo_dir)
    if not patch_result.success:
        logger.warning(
            "Some patches failed: %s — continuing anyway",
            patch_result.errors,
        )

    # Step 3: Smoke test (skip if plan says so)
    if plan.get("skip_smoke", False):
        logger.info("Step 3/5: Skipping smoke test (skip_smoke=true in plan)")
    else:
        logger.info("Step 3/5: Running smoke test for %s", paper_id)
        smoke_result = runner.smoke_test(
            paper_dir=paper_dir,
            repo_dir=repo_dir,
            venv_path=env_result.venv_path,
            plan=plan,
            timeout=smoke_timeout_secs,
        )
        if not smoke_result.success:
            _update_status(paper_dir, "smoke_failed", [], smoke_result.error)
            return {
                "paper_id": paper_id,
                "status": "smoke_failed",
                "metrics": None,
                "log_path": "",
                "run_dir": "",
                "error": f"Smoke test failed: {smoke_result.error}",
            }

    # Step 4: Scaled run
    logger.info("Step 4/5: Running scaled experiment for %s", paper_id)
    scaled_result = runner.scaled_run(
        paper_dir=paper_dir,
        repo_dir=repo_dir,
        venv_path=env_result.venv_path,
        plan=plan,
        overrides=scaled_config_overrides,
        budget_secs=wall_clock_budget_secs,
    )

    run_dir = scaled_result.run_dir or ""
    log_path = scaled_result.output_log or ""

    if scaled_result.timed_out:
        # Timeout: still extract whatever metrics we can
        extracted = {}
        if run_dir:
            extracted = metrics.extract(run_dir, plan.get("metrics_to_capture", []))
        artifacts = []
        if log_path:
            artifacts.append(os.path.relpath(log_path, paper_dir))
        _update_status(paper_dir, "timeout", artifacts, scaled_result.error)
        return {
            "paper_id": paper_id,
            "status": "timeout",
            "metrics": extracted.get("metrics"),
            "log_path": log_path,
            "run_dir": run_dir,
            "error": scaled_result.error,
        }

    if not scaled_result.success:
        artifacts = []
        if log_path:
            artifacts.append(os.path.relpath(log_path, paper_dir))
        _update_status(paper_dir, "failed", artifacts, scaled_result.error)
        return {
            "paper_id": paper_id,
            "status": "failed",
            "metrics": None,
            "log_path": log_path,
            "run_dir": run_dir,
            "error": f"Scaled run failed: {scaled_result.error}",
        }

    # Step 5: Extract metrics
    logger.info("Step 5/5: Extracting metrics for %s", paper_id)
    metrics_to_capture = plan.get("metrics_to_capture", ["loss"])
    extracted = metrics.extract(run_dir, metrics_to_capture)

    artifacts = []
    if log_path:
        artifacts.append(os.path.relpath(log_path, paper_dir))
    results_json = os.path.join(run_dir, "results.json")
    if os.path.isfile(results_json):
        artifacts.append(os.path.relpath(results_json, paper_dir))

    _update_status(paper_dir, "success", artifacts)

    return {
        "paper_id": paper_id,
        "status": "ok",
        "metrics": extracted.get("metrics"),
        "log_path": log_path,
        "run_dir": run_dir,
        "error": None,
    }


@mcp.tool()
def scaled_runner(
    paper_id: str,
    plan: dict,
    scaled_config_overrides: Optional[dict] = None,
    wall_clock_budget_secs: int = 7200,
    smoke_timeout_secs: int = 120,
) -> dict[str, Any]:
    """Run a scaled paper reproduction experiment.

    Given a paper_id and plan.json content, sets up the environment,
    applies patches, runs a smoke test, executes the scaled experiment,
    and extracts metrics.

    Args:
        paper_id: Identifier for the paper (directory name under papers/)
        plan: The plan.json content with train_script, train_args, scaled_config,
              smoke_config, and metrics_to_capture fields
        scaled_config_overrides: Optional overrides for batch_size, steps,
                                  dataset_fraction, etc.
        wall_clock_budget_secs: Wall-clock time budget for the scaled run (default 7200 = 2h)
        smoke_timeout_secs: Timeout for the smoke test (default 120s)

    Returns:
        Dict with paper_id, status (ok/timeout/failed/smoke_failed),
        metrics, log_path, run_dir, and error fields
    """
    return run_pipeline(
        paper_id=paper_id,
        plan=plan,
        scaled_config_overrides=scaled_config_overrides,
        wall_clock_budget_secs=wall_clock_budget_secs,
        smoke_timeout_secs=smoke_timeout_secs,
    )


def main():
    """Entry point: MCP server or --cli mode."""
    if "--cli" in sys.argv:
        # CLI mode: read plan from stdin or file argument
        if len(sys.argv) < 3:
            print("Usage: python server.py --cli <paper_id> [plan.json path]", file=sys.stderr)
            sys.exit(1)

        paper_id = sys.argv[2]
        plan_path = sys.argv[3] if len(sys.argv) > 3 else None

        if plan_path:
            with open(plan_path, "r") as f:
                plan = json.load(f)
        else:
            # Auto-discover plan.json from paper directory
            auto_path = os.path.join(PAPERS_DIR, paper_id, "plan.json")
            if os.path.isfile(auto_path):
                print(f"Reading plan from {auto_path}", file=sys.stderr)
                with open(auto_path, "r") as f:
                    plan = json.load(f)
            else:
                print("Reading plan from stdin...", file=sys.stderr)
                plan = json.load(sys.stdin)

        # Use smoke timeout from plan if specified, otherwise default
        smoke_timeout = plan.get("smoke_config", {}).get("timeout_seconds", 600)
        result = run_pipeline(paper_id=paper_id, plan=plan, smoke_timeout_secs=smoke_timeout)
        print(json.dumps(result, indent=2))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
