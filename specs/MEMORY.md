# Memory

- No additional memory-only indications right now.
- Canonical workspace rules and PowerShell execution guidance live in `AGENTS.md`.
- Only two repos currently contain `setup_wizard.py`: `arr-helper-ui` and `prowlarr-ui`; this file is not template-managed in `aatemplate`.
- `aatemplate` is a Copier template repo without a root `pyproject.toml`; `uv sync` is not applicable there.
- PowerShell 5.1 does not support `&&`; use compatible separators/flow (`;`, `if ($LASTEXITCODE -ne 0) { ... }`) instead.
- In PowerShell batch pytest loops, avoid `"$r: ..."` interpolation because `$r:` triggers a parser error (`InvalidVariableReferenceWithDrive`); use `"${repo}: ..."` (or `${r}`) in interpolated strings.
- Prefer literal here-strings `@' ... '@` for script bodies; use expandable here-strings `@" ... "@` only when interpolation is required.
- If using `@" ... "@`, escape script-local `$` as `` `$ `` so variables like `$_`, `$ln`, and `$LASTEXITCODE` are not expanded too early.
- In literal here-strings, write normal `'text'` and avoid accidental over-escaping like `''text''`.
- Ensure not to hit Windows command-length limits, so break commands into file-sized patches or use supporting python scripts instead.
- User shorthand: `cuus` means "commit and push to GitHub."
