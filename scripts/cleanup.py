"""Workspace cleanup CLI for removing generated artifacts safely.

This utility scans the current Python workspace recursively and removes common
temporary directories and files such as ``__pycache__`` and tool caches. It
supports explicit command-line flags for automation and a numeric interactive
menu when launched without cleanup arguments.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 3

REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)

BASIC_DIRECTORY_CATEGORIES: dict[str, str] = {
    "__pycache__": "cache",
    ".pytest_cache": "cache",
    ".ruff_cache": "cache",
    ".mypy_cache": "cache",
    ".hypothesis": "cache",
    ".tox": "cache",
    ".nox": "cache",
    ".cache": "cache",
    ".eggs": "cache",
    ".tmp_test_data": "temp",
    "tmp_config_override": "temp",
}
DEEP_DIRECTORY_CATEGORIES: dict[str, str] = {
    "build": "build",
    "dist": "build",
    "htmlcov": "coverage",
}
DEEP_FILE_CATEGORIES: dict[str, str] = {
    ".coverage": "coverage",
    "coverage.xml": "coverage",
}
VENV_DIRECTORY_CATEGORIES: dict[str, str] = {
    ".venv": "venv",
    "venv": "venv",
    "env": "venv",
}


class CleanupScope(StrEnum):
    """Named cleanup scopes supported by the CLI."""

    BASIC = "basic"
    DEEP = "deep"
    VENV = "venv"


@dataclass(frozen=True, slots=True)
class CleanupRequest:
    """Resolved cleanup request settings.

    Attributes:
        scopes: Cleanup scopes to apply.
        dry_run: Whether execution should only preview deletions.
        source_label: Human-readable description of how the request was chosen.
    """

    scopes: frozenset[CleanupScope]
    dry_run: bool
    source_label: str


@dataclass(frozen=True, slots=True)
class CleanupTarget:
    """Represents a file-system target selected for cleanup.

    Attributes:
        path: Absolute path to the file or directory to remove.
        category: Reporting bucket such as ``cache`` or ``venv``.
        is_directory: Whether the target is a directory.
    """

    path: Path
    category: str
    is_directory: bool

    def relative_to(self, workspace_root: Path) -> Path:
        """Return the path relative to the workspace root.

        Args:
            workspace_root: Root directory of the workspace.

        Returns:
            Relative path from the workspace root to this target.
        """

        return self.path.relative_to(workspace_root)


@dataclass(frozen=True, slots=True)
class MenuOption:
    """Interactive numeric menu entry.

    Attributes:
        number: Displayed numeric choice.
        label: Human-readable menu label.
        request: Cleanup request represented by this menu choice.
        is_cancel: Whether the entry cancels execution.
    """

    number: str
    label: str
    request: CleanupRequest | None
    is_cancel: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for workspace cleanup.

    Returns:
        Configured argument parser.
    """

    parser = argparse.ArgumentParser(
        prog="cleanup.py",
        description="Clean temporary workspace artifacts recursively.",
    )
    parser.add_argument(
        "--clean-basic",
        action="store_true",
        help="Remove safe cache and temporary artifact directories.",
    )
    parser.add_argument(
        "--clean-deep",
        action="store_true",
        help="Remove basic targets plus build and coverage artifacts.",
    )
    parser.add_argument(
        "--clean-venv",
        action="store_true",
        help="Remove virtual environment directories only.",
    )
    parser.add_argument(
        "--clean-nuclear",
        action="store_true",
        help="Remove deep cleanup targets plus virtual environments.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview cleanup targets without deleting them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip deletion confirmation prompts.",
    )
    return parser


def resolve_workspace_root() -> Path:
    """Resolve the workspace root from this script location.

    Returns:
        Absolute workspace root path.
    """

    return Path(__file__).resolve().parents[2]


def resolve_request(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> CleanupRequest | None:
    """Resolve the requested cleanup mode from parsed CLI arguments.

    Args:
        parser: Parser used to report invalid combinations.
        args: Parsed command-line arguments.

    Returns:
        Cleanup request, or ``None`` when interactive menu mode should be used.
    """

    has_cleanup_flag = bool(
        args.clean_basic or args.clean_deep or args.clean_venv or args.clean_nuclear
    )
    if not has_cleanup_flag:
        return None

    if args.clean_nuclear and (args.clean_basic or args.clean_deep or args.clean_venv):
        parser.error("--clean-nuclear cannot be combined with other cleanup flags.")

    if args.clean_nuclear:
        return CleanupRequest(
            scopes=frozenset(
                {CleanupScope.BASIC, CleanupScope.DEEP, CleanupScope.VENV}
            ),
            dry_run=args.dry_run,
            source_label="nuclear cleanup",
        )

    scopes: set[CleanupScope] = set()
    if args.clean_basic:
        scopes.add(CleanupScope.BASIC)
    if args.clean_deep:
        scopes.update({CleanupScope.BASIC, CleanupScope.DEEP})
    if args.clean_venv:
        scopes.add(CleanupScope.VENV)

    return CleanupRequest(
        scopes=frozenset(scopes),
        dry_run=args.dry_run,
        source_label="command-line cleanup",
    )


def build_menu_options() -> tuple[MenuOption, ...]:
    """Build the numeric interactive menu options.

    Returns:
        Ordered tuple of menu options.
    """

    safe_scope = frozenset({CleanupScope.BASIC})
    deep_scope = frozenset({CleanupScope.BASIC, CleanupScope.DEEP})
    nuclear_scope = frozenset(
        {CleanupScope.BASIC, CleanupScope.DEEP, CleanupScope.VENV}
    )
    venv_scope = frozenset({CleanupScope.VENV})
    return (
        MenuOption("1", "Safe cleanup", CleanupRequest(safe_scope, False, "menu")),
        MenuOption("2", "Safe cleanup (dry-run)", CleanupRequest(safe_scope, True, "menu")),
        MenuOption("3", "Deep cleanup", CleanupRequest(deep_scope, False, "menu")),
        MenuOption("4", "Deep cleanup (dry-run)", CleanupRequest(deep_scope, True, "menu")),
        MenuOption(
            "5",
            "Nuclear cleanup",
            CleanupRequest(nuclear_scope, False, "menu"),
        ),
        MenuOption(
            "6",
            "Nuclear cleanup (dry-run)",
            CleanupRequest(nuclear_scope, True, "menu"),
        ),
        MenuOption(
            "7",
            "Venv cleanup only",
            CleanupRequest(venv_scope, False, "menu"),
        ),
        MenuOption(
            "8",
            "Venv cleanup only (dry-run)",
            CleanupRequest(venv_scope, True, "menu"),
        ),
        MenuOption("9", "Cancel", None, is_cancel=True),
    )


def prompt_for_request() -> CleanupRequest | None:
    """Prompt the user to select a cleanup mode numerically.

    Returns:
        Cleanup request for the chosen option, or ``None`` if cancelled.
    """

    options = build_menu_options()
    print("Workspace cleanup options:")
    for option in options:
        print(f"{option.number}. {option.label}")
    while True:
        selection = input("Select an option [1-9]: ").strip()
        for option in options:
            if option.number != selection:
                continue
            if option.is_cancel:
                return None
            return option.request
        print("Invalid selection. Enter a number from 1 to 9.")


def is_reparse_point(path: Path) -> bool:
    """Return whether a path is a reparse point or symlink.

    Args:
        path: Path to inspect.

    Returns:
        ``True`` when the path is a symlink or Windows reparse point.
    """

    try:
        if path.is_symlink():
            return True
        return bool(path.lstat().st_file_attributes & REPARSE_POINT_ATTRIBUTE)
    except (AttributeError, OSError):
        return False


def should_prune_directory(name: str, request: CleanupRequest) -> bool:
    """Return whether a directory should be pruned from traversal.

    Args:
        name: Directory name under evaluation.
        request: Cleanup request controlling traversal.

    Returns:
        ``True`` when the directory should not be traversed.
    """

    if name == ".git":
        return True
    return CleanupScope.VENV not in request.scopes and name in VENV_DIRECTORY_CATEGORIES


def classify_directory(name: str, request: CleanupRequest) -> str | None:
    """Classify a directory name as a cleanup target.

    Args:
        name: Directory name to classify.
        request: Cleanup request controlling target selection.

    Returns:
        Category name for the matched target, or ``None``.
    """

    if CleanupScope.VENV in request.scopes and name in VENV_DIRECTORY_CATEGORIES:
        return VENV_DIRECTORY_CATEGORIES[name]
    if name.endswith(".egg-info") and CleanupScope.BASIC in request.scopes:
        return "cache"
    if CleanupScope.DEEP in request.scopes and name in DEEP_DIRECTORY_CATEGORIES:
        return DEEP_DIRECTORY_CATEGORIES[name]
    if CleanupScope.BASIC in request.scopes and name in BASIC_DIRECTORY_CATEGORIES:
        return BASIC_DIRECTORY_CATEGORIES[name]
    return None


def classify_file(name: str, request: CleanupRequest) -> str | None:
    """Classify a file name as a cleanup target.

    Args:
        name: File name to classify.
        request: Cleanup request controlling target selection.

    Returns:
        Category name for the matched file, or ``None``.
    """

    if CleanupScope.DEEP not in request.scopes:
        return None
    return DEEP_FILE_CATEGORIES.get(name)


def ensure_within_workspace(path: Path, workspace_root: Path) -> None:
    """Validate that a target resolves under the workspace root.

    Args:
        path: Candidate path to validate.
        workspace_root: Workspace root boundary.

    Raises:
        ValueError: If the path escapes the workspace root.
    """

    resolved_root = workspace_root.resolve(strict=True)
    resolved_path = path.resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"Refusing to touch path outside workspace: {path}")


def discover_targets(workspace_root: Path, request: CleanupRequest) -> list[CleanupTarget]:
    """Discover cleanup targets recursively under the workspace root.

    Args:
        workspace_root: Workspace root to scan.
        request: Cleanup request controlling discovery.

    Returns:
        Planned cleanup targets ordered for safe deletion.
    """

    ensure_within_workspace(workspace_root, workspace_root)
    candidates: list[CleanupTarget] = []
    for current_root, dir_names, file_names in os.walk(
        workspace_root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_root)
        retained_dir_names: list[str] = []
        for dir_name in dir_names:
            dir_path = current_path / dir_name
            if is_reparse_point(dir_path):
                continue
            category = classify_directory(dir_name, request)
            if category is not None:
                ensure_within_workspace(dir_path, workspace_root)
                candidates.append(
                    CleanupTarget(path=dir_path, category=category, is_directory=True)
                )
                continue
            if should_prune_directory(dir_name, request):
                continue
            retained_dir_names.append(dir_name)
        dir_names[:] = retained_dir_names

        for file_name in file_names:
            file_path = current_path / file_name
            if is_reparse_point(file_path):
                continue
            category = classify_file(file_name, request)
            if category is None:
                continue
            ensure_within_workspace(file_path, workspace_root)
            candidates.append(
                CleanupTarget(path=file_path, category=category, is_directory=False)
            )
    return plan_targets(workspace_root, candidates)


def plan_targets(
    workspace_root: Path, candidates: Iterable[CleanupTarget]
) -> list[CleanupTarget]:
    """Deduplicate and order targets for safe deletion.

    Args:
        workspace_root: Workspace root boundary.
        candidates: Candidate targets discovered during scanning.

    Returns:
        Deduplicated targets ordered deepest-first for deletion.
    """

    unique_targets: dict[Path, CleanupTarget] = {}
    for candidate in candidates:
        ensure_within_workspace(candidate.path, workspace_root)
        unique_targets[candidate.path] = candidate

    kept_directory_paths: list[Path] = []
    filtered_targets: list[CleanupTarget] = []
    sorted_candidates = sorted(
        unique_targets.values(),
        key=lambda target: (len(target.path.parts), str(target.path).lower()),
    )
    for candidate in sorted_candidates:
        if any(candidate.path.is_relative_to(parent) for parent in kept_directory_paths):
            continue
        filtered_targets.append(candidate)
        if candidate.is_directory:
            kept_directory_paths.append(candidate.path)

    return sorted(
        filtered_targets,
        key=lambda target: (
            len(target.path.parts),
            0 if target.is_directory else 1,
            str(target.path).lower(),
        ),
        reverse=True,
    )


def summarize_categories(targets: Sequence[CleanupTarget]) -> list[str]:
    """Build human-readable category summary lines.

    Args:
        targets: Targets to summarize.

    Returns:
        Formatted summary lines ordered alphabetically by category.
    """

    category_counts = Counter(target.category for target in targets)
    return [
        f"  - {category}: {count}"
        for category, count in sorted(category_counts.items(), key=lambda item: item[0])
    ]


def render_paths(workspace_root: Path, targets: Sequence[CleanupTarget]) -> list[str]:
    """Build display lines for planned target paths.

    Args:
        workspace_root: Workspace root used to show relative paths.
        targets: Targets to display.

    Returns:
        Display lines for the planned target paths.
    """

    ordered_paths = sorted(
        (target.relative_to(workspace_root) for target in targets),
        key=lambda path: str(path).lower(),
    )
    return [f"  - {path}" for path in ordered_paths]


def print_plan(workspace_root: Path, request: CleanupRequest, targets: Sequence[CleanupTarget]) -> None:
    """Print the planned cleanup summary.

    Args:
        workspace_root: Workspace root used for relative path display.
        request: Cleanup request being executed.
        targets: Planned targets.
    """

    mode_label = "DRY-RUN" if request.dry_run else "DELETE"
    scope_names = ", ".join(sorted(scope.value for scope in request.scopes))
    print(f"{mode_label} plan for scopes: {scope_names}")
    print(f"Workspace root: {workspace_root}")
    print(f"Targets found: {len(targets)}")
    if not targets:
        return
    print("Categories:")
    for line in summarize_categories(targets):
        print(line)
    print("Paths:")
    for line in render_paths(workspace_root, targets):
        print(line)


def confirm_deletion(target_count: int) -> bool:
    """Prompt the user to confirm deletion.

    Args:
        target_count: Number of targets about to be deleted.

    Returns:
        ``True`` when deletion is confirmed.
    """

    prompt = f"Delete {target_count} target(s)? [y/N]: "
    while True:
        response = input(prompt).strip().lower()
        if response in {"y", "yes"}:
            return True
        if response in {"", "n", "no"}:
            return False
        print("Invalid response. Enter y or n.")


def execute_targets(targets: Sequence[CleanupTarget]) -> list[str]:
    """Delete the planned cleanup targets.

    Args:
        targets: Targets ordered for deletion.

    Returns:
        Error messages for any failed deletions.
    """

    failures: list[str] = []
    for target in targets:
        try:
            if target.is_directory:
                if target.path.exists():
                    shutil.rmtree(target.path)
            elif target.path.exists():
                target.path.unlink()
        except OSError as exc:
            failures.append(f"{target.path}: {exc}")
    return failures


def run_cleanup(
    workspace_root: Path, request: CleanupRequest, *, auto_confirm: bool
) -> int:
    """Run the cleanup workflow for a resolved request.

    Args:
        workspace_root: Workspace root to clean.
        request: Cleanup request to execute.
        auto_confirm: Whether real deletions should skip confirmation.

    Returns:
        Process-style exit code.
    """

    targets = discover_targets(workspace_root, request)
    print_plan(workspace_root, request, targets)
    if not targets:
        print("Nothing to clean.")
        return EXIT_SUCCESS
    if request.dry_run:
        print("Dry-run complete. No files or directories were deleted.")
        return EXIT_SUCCESS
    if not auto_confirm and not confirm_deletion(len(targets)):
        print("Cleanup cancelled.")
        return EXIT_CANCELLED

    failures = execute_targets(targets)
    if failures:
        print("Cleanup completed with failures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return EXIT_FAILURE

    print(f"Deleted {len(targets)} target(s).")
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for workspace cleanup.

    Args:
        argv: Optional argument sequence. Uses ``sys.argv[1:]`` when omitted.

    Returns:
        Process-style exit code.
    """

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    request = resolve_request(parser, args)
    if request is None:
        request = prompt_for_request()
        if request is None:
            print("Cleanup cancelled.")
            return EXIT_CANCELLED
    workspace_root = resolve_workspace_root()
    return run_cleanup(workspace_root, request, auto_confirm=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
