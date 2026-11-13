---
name: python-codebase
description: Navigate, test, and debug Python codebases methodically — environment discipline, packaging pitfalls, pdb/pytest workflows, import-time surprises. Use when a Python repo is confusing, under-documented, or failing in ways that resist quick fixes.
when_to_use: Unfamiliar Python repo; import errors; tests pass locally but fail in CI; slow startup; mysterious isinstance/subclass behavior; dependency version drift.
allowed-tools: [run_shell, read_file, grep, glob]
argument-hint: <path or the failure symptom>
---

# Python Codebase Playbook

## 1. Reproduce and scope first
- `python --version` and `python -c "import sys; print(sys.executable)"` — never debug
  until you know which interpreter and which stdlib you have.
- `git status --short` / `git stash` — is the repo clean? Uncommitted changes explain
  half of all "mysteries".
- `python -X dev -m pytest -x -q --lf` — re-run only failing tests, dev warnings on.

## 2. Map the project in 3 minutes
- `pyproject.toml` / `setup.py` / `requirements*.txt` — dependencies and entry points.
- `find . -name '__init__.py' -path '*pkg*' -o -name 'conftest.py'` — package layout.
- `pytest --collect-only -q | head -30` — what is actually tested.
- `grep -rn "import " --include=*.py | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head` — who imports what.

## 3. Import-time traps
- Heavy work at import time (network calls, file reads, subprocesses) is the #1 cause
  of hangs "during import". Search: `grep -rn "requests.get\|urlopen\|subprocess" --include=*.py`.
- Circular imports: if you see `ImportError: cannot import name`, trace the import
  chain with `python -X importtime -c "import pkg"` (log as ms importtime.log).
- Namespace packages shadowing: `python -c "import pkg; print(pkg.__file__, pkg.__path__)"`.

## 4. Test discipline
- Minimal failing case: `pytest tests/test_x.py::test_y -vv --pdb` (or `--tb=long`).
- Fixtures live in `conftest.py`; `pytest --fixtures -q | grep -A2 fixturename`.
- Never mark a flake with `@pytest.mark.skip` — attach a note with the reproducer
  and the date, or delete the test.

## 5. Performance triage
- `python -X importtime -c "import slowpkg"` — import cost.
- `python -m cProfile -s cumulative script.py | head -20` — hot paths.
- `python -m memory_profiler script.py | head -20` — allocation hogs.
- If >85% of time is a single C-extension call, no amount of Python-level tuning helps;
  profile before optimizing.

## 6. When stuck
- Bisect with `git bisect start; git bisect bad; git bisect good <sha>`.
- `python -W error -X dev` turns warnings into failures — find latent bugs fast.
- Write the smallest possible reproduction in a scratch file; 90% of "impossible" bugs
  dissolve under a 20-line repro.
