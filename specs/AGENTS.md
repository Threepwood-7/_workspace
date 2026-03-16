# AGENTS.md

## AI Coding Agent Directives (MANDATORY – follow in EVERY interaction)

You are a senior Python engineer working in a project that enforces **zero-tolerance** code quality.

**Before you output any code you MUST mentally verify it passes all of these checks:**

### 1. Toolchain Enforcement (Non-negotiable)
- Code must pass **100%** of checks: fmt, fix, types, deps, deadcode, complexity, policy
- If you cannot make it pass, say exactly what fails and propose the fix.

### 2. Code Style & Structure (Ruff-enforced)
- Line length exactly as dictated by ruff
- Use modern Python 3.13+ features (`|` for unions, `match`, etc.)
- All functions/classes must have Google-style docstrings
- Never use `Any`, `Optional` where a concrete type exists

### 3. Type Safety (basedpyright strict)
- Every function parameter and return value must be typed
- No untyped variables, no `# type: ignore` unless you explain why
- Use generics, TypeVars, Protocols, and `reveal_type` when needed
- AVOID using cast(). Use cast only when
  - the type is guaranteed by logic
  - the type checker cannot infer it
  - Avoid using it as a quick fix for type errors
- Most typing solved with
  - TypedDict
  - Protocol
  - TypeGuard
  - good return types

### 5. Dependencies (deptry + pyproject.toml)
- Only import packages that are already declared in `[project.dependencies]` or `[tool.hatch.envs.default.dependencies]`
- If you need a new dependency, say "Add X to pyproject.toml" — never just import it

### 6. Dead Code (Vulture)
- Never introduce unused functions, classes, imports, or variables
- If you see dead code, propose its removal

**DO**:
- DO Keep functions small
- DO Use type hints everywhere
- DO Write tests first when adding features
- DO Run full lint suite after adding new features and new py files

**DO NOT**:
- DO NOT Add `# noqa` unless absolutely required (explain)
- DO NOT Hard-code strings that belong in config
- DO NOT Use `print()` for debugging in production code
- DO NOT Include local file paths, names, or any other local-machine specific information to any committed code, or documentation. Only allowed exception are common paths like c:\bin, c:\Program Files, c:\Windows, or c:\tmp

DO follow these rules religiously and you will produce production-grade, zero-defect Python every single time.

## Quick Startup Project Map

- `aatemplate` - source Copier template for this workspace; template-applicable changes start here. `aatemplate` is module-first. Do not add `src/<package>/main.py` as a required template file. If executable support is needed, keep it in `src/<package>/__main__.py` only, so `python -m <package>` works without a separate `main.py`.
- `arr-helper-ui` - Sonarr UI helper and media quality checker toolkit.
- `git-statuz` - PySide viewer for Git status and history.
- `many-panelz-explorer` - multi-panel Windows-focused file explorer built with PySide6.
- `mp3gain-gui-py` - PySide6 port of MP3Gain GUI for ReplayGain analysis and gain adjustment.
- `prowlarr-ui` - Windows desktop application for searching Prowlarr indexers with Everything integration.
- `qbiremo-enhanced` - advanced qBittorrent GUI client built with PySide6.
- `threep-commons` - shared reusable runtime and utility library for the Threepwood PySide project family.
- `video-duperz` - Windows-first PySide app for perceptual duplicate video detection.
- `web-pagez-to-pdf` - Windows-first PySide app for capturing previous-window screenshots.
- `_workspace` - shared unversioned support folder for cross-project scripts, specs, and snippets.

## Standardization

- Print the *local PC time* HH:mm:ss time alongside messages by doing an `ECHO %TIME%`, so I know what you are doing.
- Always load `MEMORY.md` together with this file before starting work.
- `aatemplate` is the source Copier template project for this workspace. Code quality checks should be applied to it too.
- Validate `aatemplate` by rendering fresh sample projects and running quality checks in the rendered output; do not treat the raw `aatemplate` repo root as a normal Hatch project, and do not expect `hatch run lint:*` to work there directly.
- All other sibling projects under this directory are Copier-managed targets that should be synced/updated from `aatemplate` (not treated as the template source).
- Ensure to comment methods, classes, and complex logic with concise but effective and easy to parse comments.
- Ensure to follow best design standards, favor composition, Separation of Concerns, DRY, PEP 20
- Prefer Python pathlib Path usage, and leverage PureWindowsPath to format Windows Paths.
- Ensure to perform code linting, type checking, complexity checks, deadcode checks, basedpyright, deptry, ruff, and formatting with `hatch run lint:{check,fmt,types,deps,deadcode,complexity,policy}` whenever a significant change or refactoring is introduced.
- All new or modified code MUST pass linting, Ruff, and basedpyright checks as real fixes, not by suppression.
- Do NEVER suppress, skip, downgrade, or config-disable lint, Ruff, basedpyright, or related quality checks for new code. No `noqa`, no `type: ignore`, no per-file ignores, no rule downgrades, and no temporary bypasses unless the user explicitly approves an exception for an unavoidable framework constraint.
- Never generate or keep `.bat` , `.cmd` , `.ps1` scripts in template outputs; use Python scripts instead.
- git commit messages should be written in Shakespeare-style old english.
- All projects under this directory should follow the same coding guidelines, high-level design approaches, configuration handling, etc. They should all be consistent among each other.
- This set of applications is targeted to technical users that love an effective minimalist UI approach, and great technical details
- Release tags should follow a r-0.1.1 pattern where only minor .1 is updated unless specifically instructed

## Command Execution Rule

- Be AWARE that you are running on Windows 10, PowerShell version 5.1
- Prefer Python for non-trivial system command execution; use PowerShell only for basic commands.
- When generating temporary PowerShell scripts, avoid nested quote/escape patterns that can break parsing.
- Before execution, keep generated scripts parse-safe with minimal quoting complexity.
- DOS commands will require confirmation, especially any DOS command that involves a FOR or FORFILES
- You are allowed to use c:\tmp\pycompa to create temporary files, be SURE not to change anything outside of it
- ALWAYS use LF line-endings, do NOT use CRLF
- do NOT use UTF8 BOM
- Treat this as the default behavior for ALL tasks in this repository.
- When running Python tests, ensure package imports resolve from `src/` layout:
  - Prefer the project runner/environment (`hatch run test`, project scripts, or equivalent), OR
  - Explicitly set `PYTHONPATH` to the project `src` directory before invoking `pytest`.
  - Do not report import-time test failures caused only by missing `PYTHONPATH` without rerunning correctly.

## Safety Rule for System Commands

- Default to non-destructive operations.
- Do not run destructive commands unless the user explicitly asks for them, in example deleting directories
- If Deleting directories, ALWAYS do a dry run first and ensure that what you are deleting is only within the boundaries of this directory and sub-directories
- For QT UI tests, avoid bypassing monkeypatch seams around modal dialogs.
- If QT UI tests hang, suspect a real blocking dialog path (for example `QMessageBox`) and route through seam methods (for example `window._prompt_conflict_resolution`) so tests can intercept and remain non-blocking.

## Template-First Change Policy

For Copier-managed projects in this workspace:

1. Do not apply template-applicable changes directly in child repos.
2. Apply template-applicable changes in `aatemplate` first.
3. Propagate those changes to child repos only through `copier update`.
4. Direct child-repo edits are allowed only for repo-specific changes that are not template-applicable.

## Changelog Policy

- For a project, record only significant functional/technical changes in `docs/CHANGELOG.md`.
- Do not add changelog entries for minor cosmetic edits, wording-only tweaks, or trivial non-behavioral cleanup.

## Refactor Import Policy

- Keep import strategy consistent and explicit across the codebase.
- Do not introduce wrappers or legacy import mappings during refactors.
- When refactoring is requested, allow breaking import changes and update all call sites directly to the new module paths. Prefer breaking changes to achieve a better code quality or design.
- Do intermediate commits during refactoring.
- When performing code refactor, splitting of classes, app settings changes:
  - it is OK breaking public APIs, even across different projects / modules
  - no legacy wrapper should be created, focus on the refactor target
  - legacy settings are ALWAYS to be ignored and dropped, no mapping, no wrappers, no imports

## Qt Widget Naming Policy

For all Qt applications in this workspace, use a clear and consistent widget naming contract like `many-panelz-explorer`:

- assign deterministic `objectName` values to key widgets
- also set stable `widget_id` and human-readable `widget_alias` properties
- use a predictable hierarchy for IDs/aliases (window, panel, tab, control, file list, etc.)
- keep naming stable across runs so tests, diagnostics, and widget maps remain reliable
