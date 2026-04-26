#!/usr/bin/env python3
"""
Self-contained integration test for the scaled_runner pipeline.

Creates a temp directory simulating a paper directory with a tiny
training script, a minimal plan.json, and runs the full pipeline:
env setup -> (no patches) -> smoke test -> scaled run -> metrics extraction.
"""

import json
import os
import shutil
import sys
import tempfile

# Add the tool directory to path so we can import modules
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOL_DIR)

# Toy training script: loop N steps, print decreasing loss
TOY_TRAIN_SCRIPT = """\
import argparse
import math
import random

parser = argparse.ArgumentParser()
parser.add_argument("--steps", type=int, default=10)
parser.add_argument("--batch_size", type=int, default=4)
parser.add_argument("--lr", type=float, default=0.01)
args = parser.parse_args()

initial_loss = 2.5
for step in range(args.steps):
    # Simulate decreasing loss with some noise
    decay = math.exp(-0.1 * step)
    noise = random.uniform(-0.05, 0.05)
    loss = initial_loss * decay + noise
    acc = min(1.0, 0.3 + 0.06 * step + random.uniform(-0.02, 0.02))
    print(f"step: {step}, loss: {loss:.6f}, accuracy: {acc:.4f}, batch_size: {args.batch_size}")

print(f"Training complete. Final loss: {loss:.6f}")
"""

PLAN = {
    "train_script": "train.py",
    "train_args": {
        "lr": 0.01,
    },
    "smoke_config": {
        "steps": 5,
        "batch_size": 2,
    },
    "scaled_config": {
        "steps": 20,
        "batch_size": 8,
    },
    "metrics_to_capture": ["loss", "accuracy"],
}


def setup_test_environment(base_dir: str) -> tuple[str, str]:
    """
    Create a simulated paper directory structure.

    Returns (paper_dir, repo_dir).
    """
    paper_id = "test_paper_001"
    paper_dir = os.path.join(base_dir, "papers", paper_id)
    repo_dir = os.path.join(paper_dir, "repo")

    os.makedirs(repo_dir, exist_ok=True)

    # Write the toy training script
    train_script_path = os.path.join(repo_dir, "train.py")
    with open(train_script_path, "w") as f:
        f.write(TOY_TRAIN_SCRIPT)

    # Write a minimal requirements.txt (empty — no deps needed for the toy script)
    req_path = os.path.join(repo_dir, "requirements.txt")
    with open(req_path, "w") as f:
        f.write("# No external dependencies needed\n")

    # Write plan.json
    plan_path = os.path.join(paper_dir, "plan.json")
    with open(plan_path, "w") as f:
        json.dump(PLAN, f, indent=2)

    return paper_dir, repo_dir


def run_test():
    """Run the full pipeline test."""
    base_dir = tempfile.mkdtemp(prefix="scaled_runner_test_")
    print(f"Test directory: {base_dir}")

    try:
        # Setup
        paper_dir, repo_dir = setup_test_environment(base_dir)
        print(f"Paper dir: {paper_dir}")
        print(f"Repo dir:  {repo_dir}")

        # Override PAPERS_DIR to point to our test directory
        os.environ["PAPER_REPRO_PAPERS_DIR"] = os.path.join(base_dir, "papers")

        # Re-import server to pick up the env var change
        # (module-level PAPERS_DIR is evaluated at import time)
        import server
        server.PAPERS_DIR = os.path.join(base_dir, "papers")

        # Run the pipeline
        print("\n" + "=" * 60)
        print("Running scaled_runner pipeline...")
        print("=" * 60 + "\n")

        result = server.run_pipeline(
            paper_id="test_paper_001",
            plan=PLAN,
            wall_clock_budget_secs=300,  # 5 min budget for test
            smoke_timeout_secs=60,
        )

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)
        print(json.dumps(result, indent=2))

        # Validate result
        print("\n" + "=" * 60)
        print("VALIDATION:")
        print("=" * 60)

        status = result.get("status")
        print(f"  Status: {status}")

        if status == "ok":
            print("  [PASS] Pipeline completed successfully")

            metrics_data = result.get("metrics", {})
            if "loss" in metrics_data:
                loss_info = metrics_data["loss"]
                print(f"  [PASS] Loss extracted: final={loss_info.get('final')}, "
                      f"points={loss_info.get('num_points')}")
            else:
                print("  [WARN] No loss metric found in results")

            if "accuracy" in metrics_data:
                acc_info = metrics_data["accuracy"]
                print(f"  [PASS] Accuracy extracted: final={acc_info.get('final')}, "
                      f"points={acc_info.get('num_points')}")
            else:
                print("  [WARN] No accuracy metric found in results")

            # Check that output files exist
            log_path = result.get("log_path", "")
            if log_path and os.path.isfile(log_path):
                print(f"  [PASS] Output log exists: {log_path}")
            else:
                print(f"  [WARN] Output log not found: {log_path}")

            run_dir = result.get("run_dir", "")
            results_json = os.path.join(run_dir, "results.json") if run_dir else ""
            if results_json and os.path.isfile(results_json):
                print(f"  [PASS] results.json exists: {results_json}")
            else:
                print(f"  [WARN] results.json not found: {results_json}")

            # Check STATUS.json
            status_json_path = os.path.join(paper_dir, "STATUS.json")
            if os.path.isfile(status_json_path):
                with open(status_json_path) as f:
                    status_data = json.load(f)
                phases = status_data.get("phases", [])
                print(f"  [PASS] STATUS.json has {len(phases)} phase(s)")
            else:
                print("  [WARN] STATUS.json not found")

        elif status == "failed":
            print(f"  [FAIL] Pipeline failed: {result.get('error')}")
        elif status == "smoke_failed":
            print(f"  [FAIL] Smoke test failed: {result.get('error')}")
        else:
            print(f"  [INFO] Status: {status}, error: {result.get('error')}")

    finally:
        # Cleanup
        print(f"\nCleaning up: {base_dir}")
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    run_test()
