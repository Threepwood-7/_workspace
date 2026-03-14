"""Unit tests for the workspace cleanup CLI."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "cleanup.py"
MODULE_SPEC = importlib.util.spec_from_file_location("workspace_cleanup", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
cleanup = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules["workspace_cleanup"] = cleanup
MODULE_SPEC.loader.exec_module(cleanup)


class CleanupCliTests(unittest.TestCase):
    """Test the workspace cleanup CLI helpers and workflows."""

    def setUp(self) -> None:
        """Create a temporary workspace root for each test."""

        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Dispose of the temporary workspace root."""

        self.temp_dir.cleanup()

    def test_resolve_request_accepts_deep_and_venv_flags(self) -> None:
        """Resolve composed cleanup scopes from the CLI."""

        parser = cleanup.build_parser()
        args = parser.parse_args(["--clean-deep", "--clean-venv", "--dry-run"])
        request = cleanup.resolve_request(parser, args)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(
            request.scopes,
            frozenset(
                {
                    cleanup.CleanupScope.BASIC,
                    cleanup.CleanupScope.DEEP,
                    cleanup.CleanupScope.VENV,
                }
            ),
        )
        self.assertTrue(request.dry_run)

    def test_resolve_request_rejects_nuclear_combinations(self) -> None:
        """Reject incompatible cleanup flag combinations."""

        parser = cleanup.build_parser()
        args = parser.parse_args(["--clean-nuclear", "--clean-basic"])
        with self.assertRaises(SystemExit) as context:
            cleanup.resolve_request(parser, args)
        self.assertEqual(context.exception.code, cleanup.EXIT_USAGE)

    def test_prompt_for_request_maps_numeric_selection(self) -> None:
        """Map numeric menu input to the requested cleanup preset."""

        with mock.patch("builtins.input", side_effect=["6"]):
            request = cleanup.prompt_for_request()
        self.assertIsNotNone(request)
        assert request is not None
        self.assertTrue(request.dry_run)
        self.assertEqual(
            request.scopes,
            frozenset(
                {
                    cleanup.CleanupScope.BASIC,
                    cleanup.CleanupScope.DEEP,
                    cleanup.CleanupScope.VENV,
                }
            ),
        )

    def test_prompt_for_request_reprompts_after_invalid_input(self) -> None:
        """Re-prompt until a valid numeric menu choice is entered."""

        with mock.patch("builtins.input", side_effect=["bogus", "2"]):
            with mock.patch("builtins.print") as print_mock:
                request = cleanup.prompt_for_request()
        self.assertIsNotNone(request)
        assert request is not None
        self.assertTrue(request.dry_run)
        printed_messages = "\n".join(
            " ".join(str(argument) for argument in call.args)
            for call in print_mock.call_args_list
        )
        self.assertIn("Invalid selection", printed_messages)

    def test_prompt_for_request_returns_none_for_cancel(self) -> None:
        """Return cancellation when the user selects the cancel option."""

        with mock.patch("builtins.input", side_effect=["9"]):
            request = cleanup.prompt_for_request()
        self.assertIsNone(request)

    def test_discover_targets_finds_recursive_basic_junk(self) -> None:
        """Discover nested cache directories recursively."""

        target = self.workspace_root / "repo" / "src" / "__pycache__"
        target.mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC}),
            dry_run=True,
            source_label="test",
        )

        targets = cleanup.discover_targets(self.workspace_root, request)

        self.assertEqual([entry.path for entry in targets], [target])

    def test_discover_targets_skips_git_directories(self) -> None:
        """Avoid traversing inside Git metadata directories."""

        git_cache = self.workspace_root / "repo" / ".git" / "__pycache__"
        git_cache.mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC}),
            dry_run=True,
            source_label="test",
        )

        targets = cleanup.discover_targets(self.workspace_root, request)

        self.assertEqual(targets, [])

    def test_discover_targets_prunes_venv_without_venv_scope(self) -> None:
        """Skip traversing virtual environments unless explicitly requested."""

        venv_cache = self.workspace_root / "repo" / ".venv" / "Lib" / "__pycache__"
        venv_cache.mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC}),
            dry_run=True,
            source_label="test",
        )

        targets = cleanup.discover_targets(self.workspace_root, request)

        self.assertEqual(targets, [])

    def test_discover_targets_includes_venv_when_requested(self) -> None:
        """Select the venv directory itself when venv cleanup is enabled."""

        venv_dir = self.workspace_root / "repo" / ".venv"
        (venv_dir / "Lib").mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.VENV}),
            dry_run=True,
            source_label="test",
        )

        targets = cleanup.discover_targets(self.workspace_root, request)

        self.assertEqual([entry.path for entry in targets], [venv_dir])

    def test_plan_targets_deduplicates_nested_targets(self) -> None:
        """Drop child targets when a parent directory is already selected."""

        parent = self.workspace_root / "repo" / ".venv"
        child = parent / "Lib" / "__pycache__"
        planned = cleanup.plan_targets(
            self.workspace_root,
            [
                cleanup.CleanupTarget(parent, "venv", True),
                cleanup.CleanupTarget(child, "cache", True),
            ],
        )

        self.assertEqual(planned, [cleanup.CleanupTarget(parent, "venv", True)])

    def test_ensure_within_workspace_rejects_outside_paths(self) -> None:
        """Refuse to operate on paths outside the workspace root."""

        outside_path = self.workspace_root.parent / "outside-target"
        with self.assertRaises(ValueError):
            cleanup.ensure_within_workspace(outside_path, self.workspace_root)

    def test_run_cleanup_dry_run_preserves_targets(self) -> None:
        """Leave files untouched during dry-run execution."""

        self._create_deep_artifacts()
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC, cleanup.CleanupScope.DEEP}),
            dry_run=True,
            source_label="test",
        )

        rc = cleanup.run_cleanup(self.workspace_root, request, auto_confirm=False)

        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertTrue((self.workspace_root / "repo" / "__pycache__").exists())
        self.assertTrue((self.workspace_root / "repo" / "build").exists())
        self.assertTrue((self.workspace_root / "repo" / ".coverage").exists())

    def test_run_cleanup_dry_run_preserves_venv_targets(self) -> None:
        """Leave venv directories untouched during dry-run execution."""

        venv_dir = self.workspace_root / "repo" / ".venv"
        (venv_dir / "Lib").mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.VENV}),
            dry_run=True,
            source_label="test",
        )

        rc = cleanup.run_cleanup(self.workspace_root, request, auto_confirm=False)

        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertTrue(venv_dir.exists())

    def test_run_cleanup_executes_real_deletions(self) -> None:
        """Delete targeted directories and files after confirmation."""

        self._create_deep_artifacts()
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC, cleanup.CleanupScope.DEEP}),
            dry_run=False,
            source_label="test",
        )

        rc = cleanup.run_cleanup(self.workspace_root, request, auto_confirm=True)

        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertFalse((self.workspace_root / "repo" / "__pycache__").exists())
        self.assertFalse((self.workspace_root / "repo" / "build").exists())
        self.assertFalse((self.workspace_root / "repo" / ".coverage").exists())

    def test_run_cleanup_reports_failures(self) -> None:
        """Return a failure exit code when deletion raises an error."""

        target = self.workspace_root / "repo" / "__pycache__"
        target.mkdir(parents=True)
        request = cleanup.CleanupRequest(
            scopes=frozenset({cleanup.CleanupScope.BASIC}),
            dry_run=False,
            source_label="test",
        )

        with mock.patch.object(cleanup.shutil, "rmtree", side_effect=OSError("boom")):
            rc = cleanup.run_cleanup(self.workspace_root, request, auto_confirm=True)

        self.assertEqual(rc, cleanup.EXIT_FAILURE)
        self.assertTrue(target.exists())

    def test_main_returns_cancel_for_menu_cancel(self) -> None:
        """Return the cancel exit code when the menu is cancelled."""

        with mock.patch.object(
            cleanup, "resolve_workspace_root", return_value=self.workspace_root
        ):
            with mock.patch("builtins.input", side_effect=["9"]):
                rc = cleanup.main([])
        self.assertEqual(rc, cleanup.EXIT_CANCELLED)

    def test_main_respects_menu_delete_choice(self) -> None:
        """Execute the selected cleanup preset from the numeric menu."""

        cache_dir = self.workspace_root / "repo" / "__pycache__"
        cache_dir.mkdir(parents=True)
        with mock.patch.object(
            cleanup, "resolve_workspace_root", return_value=self.workspace_root
        ):
            with mock.patch("builtins.input", side_effect=["1", "y"]):
                rc = cleanup.main([])
        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertFalse(cache_dir.exists())

    def test_main_respects_flag_dry_run_choice(self) -> None:
        """Preserve targets when dry-run is requested through CLI flags."""

        cache_dir = self.workspace_root / "repo" / "__pycache__"
        cache_dir.mkdir(parents=True)
        with mock.patch.object(
            cleanup, "resolve_workspace_root", return_value=self.workspace_root
        ):
            rc = cleanup.main(["--clean-basic", "--dry-run"])
        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertTrue(cache_dir.exists())

    def test_main_allows_menu_dry_run_choice(self) -> None:
        """Keep targets when the dry-run menu entry is selected."""

        cache_dir = self.workspace_root / "repo" / "__pycache__"
        cache_dir.mkdir(parents=True)
        with mock.patch.object(
            cleanup, "resolve_workspace_root", return_value=self.workspace_root
        ):
            with mock.patch("builtins.input", side_effect=["2"]):
                rc = cleanup.main([])
        self.assertEqual(rc, cleanup.EXIT_SUCCESS)
        self.assertTrue(cache_dir.exists())

    def _create_deep_artifacts(self) -> None:
        """Create common deep-cleanup artifacts inside the test workspace."""

        repo_root = self.workspace_root / "repo"
        (repo_root / "__pycache__").mkdir(parents=True)
        (repo_root / "build").mkdir(parents=True)
        (repo_root / ".coverage").write_text("data", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
