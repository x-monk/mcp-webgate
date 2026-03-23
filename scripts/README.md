# scripts/robot.py

`robot.py` is the project automation tool for `mcp-webgate`. It handles testing, building, versioning, releases, and development queries.

## 🚀 Usage

```
python scripts/robot.py <command> [options]
```

All commands must be run from the project root.

## 🔧 Commands

### test

Runs the full test suite with `pytest -v`.

```
python scripts/robot.py test
```

---

### build

Runs the test suite first, then compiles wheel + sdist into `dist/`. Before building, temporarily injects a changelog snippet table (last 4 entries) into `README.md` for the PyPI page, then restores it afterwards. Aborts immediately if tests fail.

```
python scripts/robot.py build
```

---

### bump

Bumps the version and commits + pushes to `dev`. Must be run on the `dev` branch.

```
python scripts/robot.py bump [X.Y.Z]
```

| Argument | Description |
|----------|-------------|
| `X.Y.Z`  | Target version. If omitted, auto-increments the patch (e.g. `0.1.19` → `0.1.20`) |

**Behavior:**
1. Reads the current version from `pyproject.toml`
2. If `CHANGELOG.md` has no entry for the new version yet, inserts a scaffold
3. Writes the new version into `pyproject.toml`, `src/mcp_webgate/__init__.py`, and updates the badge in `README.md`
4. Commits and pushes to `origin/dev`

> **Note:** Write the CHANGELOG entry **before** running bump. The robot detects an existing entry and skips scaffolding.

---

### status

Prints a project overview: current branch, versions on `dev` and `main`, last 3 CHANGELOG entries, test count, and number of uncommitted files.

```
python scripts/robot.py status
```

Example output:

```
====================================================
  mcp-webgate project status
====================================================
  branch   : dev
  dev      : v0.1.20
  main     : v0.1.19
  tests    : 42 collected
  dirty    : 3 uncommitted file(s)

  Recent releases:
    * 2026-03-23: v0.1.20 - Release title
    * 2026-03-10: v0.1.19 - Release title
    * 2026-02-28: v0.1.18 - Release title
====================================================
```

---

### install

Uninstalls `mcp-webgate` as a `uv tool`, clears the cache, rebuilds the wheel, and reinstalls it. Useful for testing the installed tool locally without publishing to PyPI.

```
python scripts/robot.py install
```

---

### run

Starts the MCP server directly from local source using `uv run`. This is the recommended way to run the server during development: no build or install step required, changes to `.py` files are picked up immediately on next restart.

```
python scripts/robot.py run [ARGS...]
```

Any extra arguments are forwarded verbatim to `mcp-webgate`.

| Argument | Description |
|----------|-------------|
| `ARGS`   | Optional CLI args passed through to the server (e.g. `--debug`, `--llm-enabled`) |

**Examples:**

```bash
python scripts/robot.py run
python scripts/robot.py run --debug --log-file %TEMP%/webgate.log
python scripts/robot.py run --debug --llm-enabled --llm-model gemma3:27b --default-backend searxng
```

> **Note:** Use `install` instead when you want to test the server as an installed tool (i.e. the exact artifact that will be published to PyPI).

---

### promote

Promotes the current version from `dev` to `main`: no-ff merge, annotated tag, push everything. Must be run on the `dev` branch.

```
python scripts/robot.py promote
```

**Behavior:**
1. Checks that tag `vX.Y.Z` does not already exist
2. Runs `build` (which includes tests) — aborts immediately on any failure
3. Checks out `main` and merges `--no-ff` from `dev`
4. Creates the annotated tag `vX.Y.Z`
5. Pushes `main`, the tag, and `dev`
6. Returns to the `dev` branch

---

### publish

Publishes the packages in `dist/` to PyPI (or TestPyPI with `-t`). Requires a prior `build` or `promote`.

```
python scripts/robot.py publish [-t]
```

| Option | Description |
|--------|-------------|
| `-t`, `--test` | Publish to TestPyPI instead of PyPI |

---

### query

Runs `webgate_query` locally using the active configuration and prints the result as JSON. Trace data is always included. Useful for quick backend testing during development.

```
python scripts/robot.py query QUERY [-n N] [-l LANG] [-b BACKEND]
```

| Option | Default | Description |
|--------|---------|-------------|
| `QUERY` | — | Search query string (required) |
| `-n`, `--num-results` | `5` | Number of results per query |
| `-l`, `--lang` | `None` | Language code, e.g. `en`, `it` |
| `-b`, `--backend` | config | Backend: `searxng`, `brave`, `tavily`, `exa`, `serpapi` |

**Examples:**

```
python scripts/robot.py query "python asyncio" -n 3 -b searxng
python scripts/robot.py query "mcp server" -l en -n 5
```

## 🔄 Release workflow

```
# 1. Write the CHANGELOG.md entry for the new version
# 2. Bump version (scaffold is skipped if entry already exists)
python scripts/robot.py bump

# 3. Check project status
python scripts/robot.py status

# 4. Promote to main (runs tests + build internally)
python scripts/robot.py promote

# 5. Publish to PyPI
python scripts/robot.py publish
```
