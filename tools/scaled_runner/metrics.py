"""
Log parsing and metrics extraction for experiment runs.

Reads output.log from a run directory, extracts requested metrics
using regex patterns for common logging formats, and writes results.json.
"""

import json
import math
import os
import re
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Common patterns for metric reporting in training scripts
# Each pattern captures the metric value as group(1)
METRIC_PATTERNS = [
    # key: value (with optional whitespace and colons)
    r"{metric_name}[:\s]+([0-9eE\+\-\.]+)",
    # key=value (common in argparse-style logging)
    r"{metric_name}\s*=\s*([0-9eE\+\-\.]+)",
    # Python dict style: {'key': value}
    r"'{metric_name}'[:\s]+([0-9eE\+\-\.]+)",
    # JSON style: {"key": value}
    r'"{metric_name}"[:\s]+([0-9eE\+\-\.]+)',
    # Prefixed with train_ or val_ or eval_
    r"(?:train_|val_|eval_){metric_name}[:\s=]+([0-9eE\+\-\.]+)",
]


def _extract_metric_values(log_content: str, metric_name: str) -> list[float]:
    """
    Extract all numeric values for a given metric from log content.

    Tries multiple common logging patterns. Returns values in order of
    appearance (i.e., the trajectory over training).
    """
    values = []
    seen_positions = set()  # avoid double-counting from overlapping patterns

    for pattern_template in METRIC_PATTERNS:
        pattern = pattern_template.format(metric_name=re.escape(metric_name))
        for match in re.finditer(pattern, log_content, re.IGNORECASE):
            pos = match.start()
            # Skip if we already captured a value near this position
            if any(abs(pos - sp) < 5 for sp in seen_positions):
                continue
            try:
                val = float(match.group(1))
                if not math.isnan(val) and not math.isinf(val):
                    values.append(val)
                    seen_positions.add(pos)
            except (ValueError, OverflowError):
                continue

    return values


def _try_parse_json_lines(log_content: str, metrics_to_capture: list[str]) -> dict[str, list[float]]:
    """
    Try to parse JSON-lines formatted output (common in modern training frameworks).

    Each line is a JSON object potentially containing metric keys.
    Returns a dict of metric_name -> list of values.
    """
    result: dict[str, list[float]] = {m: [] for m in metrics_to_capture}

    for line in log_content.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                continue
            for metric in metrics_to_capture:
                # Try direct key and common prefixed variants
                for key_variant in [metric, f"train_{metric}", f"eval_{metric}", f"val_{metric}"]:
                    if key_variant in obj:
                        val = obj[key_variant]
                        if isinstance(val, (int, float)) and math.isfinite(val):
                            result[metric].append(float(val))
                            break
        except (json.JSONDecodeError, TypeError):
            continue

    return result


def _compute_summary(values: list[float]) -> dict[str, Any]:
    """Compute summary statistics for a metric trajectory."""
    if not values:
        return {
            "final": None,
            "min": None,
            "max": None,
            "mean": None,
            "trajectory": [],
            "num_points": 0,
        }

    return {
        "final": values[-1],
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "trajectory": values,
        "num_points": len(values),
    }


def extract(run_dir: str, metrics_to_capture: list[str]) -> dict[str, Any]:
    """
    Extract metrics from a completed training run.

    Reads output.log, applies regex and JSON-lines parsing to find
    requested metrics, computes summaries, and writes results.json.

    Args:
        run_dir: Path to the run directory (contains output.log)
        metrics_to_capture: List of metric names to extract (e.g., ["loss", "accuracy"])

    Returns:
        Dict with extracted metrics, each containing final value, trajectory, and stats
    """
    output_log = os.path.join(run_dir, "output.log")

    if not os.path.isfile(output_log):
        logger.error("Output log not found: %s", output_log)
        return {"error": f"output.log not found at {output_log}", "metrics": {}}

    try:
        with open(output_log, "r") as f:
            log_content = f.read()
    except OSError as exc:
        logger.error("Failed to read output log: %s", exc)
        return {"error": f"Failed to read output.log: {exc}", "metrics": {}}

    log_size_mb = len(log_content) / (1024 * 1024)
    logger.info(
        "Parsing output.log (%.2f MB) for metrics: %s",
        log_size_mb, ", ".join(metrics_to_capture),
    )

    # Try JSON-lines parsing first (often more reliable)
    json_metrics = _try_parse_json_lines(log_content, metrics_to_capture)

    # Build result for each metric
    metrics_result: dict[str, Any] = {}

    for metric_name in metrics_to_capture:
        # Prefer JSON-lines values if we got any
        json_values = json_metrics.get(metric_name, [])
        regex_values = _extract_metric_values(log_content, metric_name)

        # Use whichever source found more data points
        if len(json_values) >= len(regex_values):
            values = json_values
            source = "json_lines"
        else:
            values = regex_values
            source = "regex"

        summary = _compute_summary(values)
        summary["source"] = source
        metrics_result[metric_name] = summary

        if values:
            logger.info(
                "Metric '%s': %d values extracted (source=%s, final=%.6f)",
                metric_name, len(values), source, values[-1],
            )
        else:
            logger.warning("Metric '%s': no values found in output", metric_name)

    # Build the full results document
    results = {
        "metrics": metrics_result,
        "log_file": output_log,
        "log_size_bytes": len(log_content),
    }

    # Write results.json to the run directory
    results_path = os.path.join(run_dir, "results.json")
    try:
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info("Results written to %s", results_path)
    except OSError as exc:
        logger.error("Failed to write results.json: %s", exc)
        results["results_write_error"] = str(exc)

    return results
