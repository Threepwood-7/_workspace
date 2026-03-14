"""Unit tests for the workspace clone helper."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "clone_all.py"
MODULE_SPEC = importlib.util.spec_from_file_location("workspace_clone_all", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
clone_all = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules["workspace_clone_all"] = clone_all
MODULE_SPEC.loader.exec_module(clone_all)


class CloneAllTests(unittest.TestCase):
    """Test clone plan building and execution helpers."""

    def setUp(self) -> None:
        """Create a temporary target root for each test."""

        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Dispose of the temporary target root."""

        self.temp_dir.cleanup()

    def test_parse_github_owner_supports_https_and_ssh(self) -> None:
        """Parse the owner from common GitHub remote URL shapes."""

        self.assertEqual(
            clone_all.parse_github_owner("https://github.com/Threepwood-7/_workspace"),
            "Threepwood-7",
        )
        self.assertEqual(
            clone_all.parse_github_owner("git@github.com:Threepwood-7/_workspace.git"),
            "Threepwood-7",
        )

    def test_detect_github_owner_falls_back_when_remote_missing(self) -> None:
        """Fall back to the default owner when origin lookup fails."""

        completed = mock.Mock(returncode=1, stdout="", stderr="missing")
        with mock.patch.object(clone_all.subprocess, "run", return_value=completed):
            owner = clone_all.detect_github_owner(self.target_root)
        self.assertEqual(owner, clone_all.DEFAULT_GITHUB_OWNER)

    def test_build_clone_entries_marks_existing_targets_as_skip(self) -> None:
        """Skip repositories whose target directories already exist."""

        existing_dir = self.target_root / "_workspace"
        existing_dir.mkdir(parents=True)

        entries = clone_all.build_clone_entries("Threepwood-7", self.target_root)

        self.assertEqual(len(entries), len(clone_all.WORKSPACE_REPOSITORIES))
        skipped = next(entry for entry in entries if entry.repo_name == "_workspace")
        self.assertEqual(skipped.action, clone_all.CloneAction.SKIP)
        self.assertEqual(skipped.reason, "target already exists")

    def test_print_plan_lists_full_clone_set(self) -> None:
        """Print every entry in the clone plan."""

        entries = clone_all.build_clone_entries("Threepwood-7", self.target_root)

        with mock.patch("builtins.print") as print_mock:
            clone_all.print_plan(entries, self.target_root, dry_run=True)

        printed_messages = "\n".join(
            " ".join(str(argument) for argument in call.args)
            for call in print_mock.call_args_list
        )
        self.assertIn("aatemplate", printed_messages)
        self.assertIn("_workspace", printed_messages)

    def test_execute_clone_plan_dry_run_does_not_call_gh(self) -> None:
        """Avoid invoking gh during dry-run mode."""

        entries = clone_all.build_clone_entries("Threepwood-7", self.target_root)
        with mock.patch.object(clone_all, "ensure_gh_available") as ensure_gh_mock:
            with mock.patch.object(clone_all.subprocess, "run") as run_mock:
                rc = clone_all.execute_clone_plan(entries, dry_run=True)
        self.assertEqual(rc, clone_all.EXIT_SUCCESS)
        ensure_gh_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_execute_clone_plan_invokes_gh_for_missing_repositories(self) -> None:
        """Clone every missing repository with gh repo clone."""

        entries = clone_all.build_clone_entries("Threepwood-7", self.target_root)
        with mock.patch.object(clone_all, "ensure_gh_available", return_value=True):
            with mock.patch.object(
                clone_all.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="", stderr=""),
            ) as run_mock:
                rc = clone_all.execute_clone_plan(entries, dry_run=False)
        self.assertEqual(rc, clone_all.EXIT_SUCCESS)
        self.assertEqual(run_mock.call_count, len(clone_all.WORKSPACE_REPOSITORIES))

    def test_execute_clone_plan_reports_failures(self) -> None:
        """Return failure when any gh clone call fails."""

        entries = clone_all.build_clone_entries("Threepwood-7", self.target_root)
        results = [
            mock.Mock(returncode=0, stdout="", stderr="")
            for _ in range(len(entries) - 1)
        ]
        results.append(mock.Mock(returncode=1, stdout="", stderr="boom"))
        with mock.patch.object(clone_all, "ensure_gh_available", return_value=True):
            with mock.patch.object(
                clone_all.subprocess,
                "run",
                side_effect=results,
            ):
                rc = clone_all.execute_clone_plan(entries, dry_run=False)
        self.assertEqual(rc, clone_all.EXIT_FAILURE)

    def test_main_uses_detected_owner_for_dry_run(self) -> None:
        """Use the detected owner when no owner override is provided."""

        with mock.patch.object(
            clone_all, "resolve_default_target_root", return_value=self.target_root
        ):
            with mock.patch.object(
                clone_all, "resolve_script_repo_root", return_value=self.target_root
            ):
                with mock.patch.object(
                    clone_all, "detect_github_owner", return_value="Threepwood-7"
                ):
                    rc = clone_all.main(["--dry-run"])
        self.assertEqual(rc, clone_all.EXIT_SUCCESS)


if __name__ == "__main__":
    unittest.main()
