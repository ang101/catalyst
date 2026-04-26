"""
Patch application for paper reproductions.

Applies .patch files from papers/<id>/patches/ to the cloned repository.
Patches are applied in sorted filename order. If a patch fails, the error
is recorded but remaining patches are still attempted.
"""

import os
import glob
import subprocess
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PatchResult:
    applied: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True if no patches failed (including the case of no patches at all)."""
        return len(self.failed) == 0

    @property
    def total(self) -> int:
        return len(self.applied) + len(self.failed)


def _find_patches(paper_dir: str) -> list[str]:
    """Find all .patch files in papers/<id>/patches/, sorted by name."""
    patches_dir = os.path.join(paper_dir, "patches")
    if not os.path.isdir(patches_dir):
        logger.info("No patches directory at %s", patches_dir)
        return []

    pattern = os.path.join(patches_dir, "*.patch")
    patches = sorted(glob.glob(pattern))
    logger.info("Found %d patch file(s) in %s", len(patches), patches_dir)
    return patches


def _apply_single_patch(patch_file: str, repo_dir: str) -> Optional[str]:
    """
    Apply a single patch file to the repo directory.

    Returns None on success, or an error string on failure.
    """
    patch_name = os.path.basename(patch_file)
    logger.info("Applying patch: %s", patch_name)

    # First, try a dry run to check if the patch applies cleanly
    check_cmd = [
        "git", "apply", "--check", "--directory", repo_dir, patch_file,
    ]
    check_result = subprocess.run(
        check_cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if check_result.returncode != 0:
        # Check if patch is already applied (common in re-runs)
        reverse_cmd = [
            "git", "apply", "--check", "--reverse", "--directory", repo_dir, patch_file,
        ]
        reverse_result = subprocess.run(
            reverse_cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if reverse_result.returncode == 0:
            logger.info("Patch %s already applied — skipping", patch_name)
            return None  # Already applied counts as success

        error_msg = (
            f"Patch dry-run failed for {patch_name}: "
            f"{check_result.stderr.strip()}"
        )
        return error_msg

    # Apply for real
    apply_cmd = [
        "git", "apply", "--directory", repo_dir, patch_file,
    ]
    apply_result = subprocess.run(
        apply_cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if apply_result.returncode != 0:
        return (
            f"Patch apply failed for {patch_name}: "
            f"{apply_result.stderr.strip()}"
        )

    logger.info("Successfully applied patch: %s", patch_name)
    return None


def apply_patches(paper_dir: str, repo_dir: str) -> PatchResult:
    """
    Apply all patches from papers/<id>/patches/ to the repository.

    Patches are applied in sorted filename order. If a patch fails,
    the failure is recorded but remaining patches are still attempted.

    Args:
        paper_dir: Path to papers/<id>/ directory
        repo_dir: Path to the cloned repository

    Returns:
        PatchResult with lists of applied/failed patches and error details
    """
    result = PatchResult()
    patches = _find_patches(paper_dir)

    if not patches:
        logger.info("No patches to apply")
        return result

    for patch_file in patches:
        patch_name = os.path.basename(patch_file)
        try:
            error = _apply_single_patch(patch_file, repo_dir)
        except subprocess.TimeoutExpired:
            error = f"Patch {patch_name} timed out after 60 seconds"
        except FileNotFoundError:
            error = f"git not found — cannot apply patches"

        if error is None:
            result.applied.append(patch_name)
        else:
            logger.error("Patch failed: %s — %s", patch_name, error)
            result.failed.append(patch_name)
            result.errors[patch_name] = error

    logger.info(
        "Patch summary: %d applied, %d failed out of %d total",
        len(result.applied), len(result.failed), result.total,
    )
    return result
