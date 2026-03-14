"""Clone the standard GitHub workspace repository set into one root folder."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

DEFAULT_GITHUB_OWNER = "Threepwood-7"
WORKSPACE_REPOSITORIES: tuple[str, ...] = (
    "aatemplate",
    "arr-helper-ui",
    "git-statuz",
    "many-panelz-explorer",
    "mp3gain-gui-py",
    "prowlarr-ui",
    "qbiremo-enhanced",
    "threep-commons",
    "video-duperz",
    "web-pagez-to-pdf",
    "_workspace",
)


class CloneAction(StrEnum):
    """Supported clone plan actions."""

    CLONE = "clone"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CloneEntry:
    """Describe a single repository clone or skip decision.

    Attributes:
        repo_name: Repository name on GitHub and local directory name.
        source_repo: GitHub `OWNER/REPO` source spec.
        target_dir: Local target directory for the clone.
        action: Whether the repository should be cloned or skipped.
        reason: Human-readable explanation for skipped entries.
    """

    repo_name: str
    source_repo: str
    target_dir: Path
    action: CloneAction
    reason: str | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for the clone helper.
    """

    parser = argparse.ArgumentParser(
        prog="clone_all.py",
        description="Clone the standard GitHub workspace repository set.",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="Directory that should contain the cloned sibling repositories.",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner or organization to clone from.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the clone plan without running gh repo clone.",
    )
    return parser


def resolve_default_target_root() -> Path:
    """Resolve the default workspace root for sibling clones.

    Returns:
        Absolute path to the parent workspace root.
    """

    return Path(__file__).resolve().parents[2]


def resolve_script_repo_root() -> Path:
    """Resolve the `_workspace` repository root that contains this script.

    Returns:
        Absolute path to the script repository root.
    """

    return Path(__file__).resolve().parents[1]


def parse_github_owner(remote_url: str) -> str | None:
    """Extract the GitHub owner from a remote URL.

    Args:
        remote_url: Git remote URL to inspect.

    Returns:
        Repository owner name, or ``None`` when the URL is unsupported.
    """

    cleaned_url = remote_url.strip()
    if not cleaned_url:
        return None
    if cleaned_url.startswith("https://github.com/"):
        suffix = cleaned_url.removeprefix("https://github.com/")
    elif cleaned_url.startswith("git@github.com:"):
        suffix = cleaned_url.removeprefix("git@github.com:")
    else:
        return None
    parts = suffix.removesuffix(".git").split("/")
    if len(parts) < 2 or not parts[0]:
        return None
    return parts[0]


def detect_github_owner(script_repo_root: Path) -> str:
    """Detect the GitHub owner from the current `_workspace` origin remote.

    Args:
        script_repo_root: Repository root used to inspect the origin remote.

    Returns:
        GitHub owner name, falling back to the workspace default.
    """

    result = subprocess.run(
        ["git", "-C", str(script_repo_root), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return DEFAULT_GITHUB_OWNER
    return parse_github_owner(result.stdout) or DEFAULT_GITHUB_OWNER


def build_clone_entries(owner: str, target_root: Path) -> list[CloneEntry]:
    """Build the clone plan for the standard repository set.

    Args:
        owner: GitHub owner to clone from.
        target_root: Root directory that should contain the sibling repositories.

    Returns:
        Planned clone entries for the workspace repository set.
    """

    entries: list[CloneEntry] = []
    for repo_name in WORKSPACE_REPOSITORIES:
        target_dir = target_root / repo_name
        source_repo = f"{owner}/{repo_name}"
        if target_dir.exists():
            entries.append(
                CloneEntry(
                    repo_name=repo_name,
                    source_repo=source_repo,
                    target_dir=target_dir,
                    action=CloneAction.SKIP,
                    reason="target already exists",
                )
            )
            continue
        entries.append(
            CloneEntry(
                repo_name=repo_name,
                source_repo=source_repo,
                target_dir=target_dir,
                action=CloneAction.CLONE,
            )
        )
    return entries


def print_plan(entries: Sequence[CloneEntry], target_root: Path, *, dry_run: bool) -> None:
    """Print the clone or dry-run plan.

    Args:
        entries: Planned clone entries.
        target_root: Root directory for the workspace structure.
        dry_run: Whether the plan is preview-only.
    """

    mode_label = "DRY-RUN" if dry_run else "CLONE"
    print(f"{mode_label} plan for target root: {target_root}")
    print(f"Repositories in plan: {len(entries)}")
    for entry in entries:
        if entry.action is CloneAction.CLONE:
            print(f"  - clone {entry.source_repo} -> {entry.target_dir}")
            continue
        reason = entry.reason or "skipped"
        print(f"  - skip  {entry.source_repo} -> {entry.target_dir} ({reason})")


def ensure_gh_available() -> bool:
    """Return whether the GitHub CLI is available.

    Returns:
        ``True`` when `gh` is callable in the current environment.
    """

    result = subprocess.run(
        ["gh", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def repository_label(count: int) -> str:
    """Return the correct noun for a repository count.

    Args:
        count: Number of repositories.

    Returns:
        Singular or plural repository label.
    """

    return "repository" if count == 1 else "repositories"


def execute_clone_plan(entries: Sequence[CloneEntry], *, dry_run: bool) -> int:
    """Run the clone plan.

    Args:
        entries: Planned clone entries.
        dry_run: Whether the plan should only be previewed.

    Returns:
        Process-style exit code.
    """

    if dry_run:
        print("Dry-run complete. No repositories were cloned.")
        return EXIT_SUCCESS

    if not ensure_gh_available():
        print("ERROR: gh CLI is not available on PATH.", file=sys.stderr)
        return EXIT_FAILURE

    failures: list[str] = []
    cloned_count = 0
    for entry in entries:
        if entry.action is CloneAction.SKIP:
            continue
        entry.target_dir.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["gh", "repo", "clone", entry.source_repo, str(entry.target_dir)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            cloned_count += 1
            continue
        stderr_text = result.stderr.strip() or result.stdout.strip() or "clone failed"
        failures.append(f"{entry.repo_name}: {stderr_text}")

    if failures:
        print("Clone run completed with failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"Cloned {cloned_count} {repository_label(cloned_count)}.")
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """Run the clone helper CLI.

    Args:
        argv: Optional CLI argument sequence.

    Returns:
        Process-style exit code.
    """

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    target_root = (
        args.target_root.resolve()
        if args.target_root is not None
        else resolve_default_target_root()
    )
    owner = args.owner or detect_github_owner(resolve_script_repo_root())
    entries = build_clone_entries(owner, target_root)
    print_plan(entries, target_root, dry_run=args.dry_run)
    return execute_clone_plan(entries, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
