#!/usr/bin/env python3
"""
robot.py — Project automation for mcp-webgate.

Commands:
  test                Run the full test suite
  build               Build PyPI wheel + sdist into dist/
  install             Uninstall, clean, rebuild, and install as uv tool
  bump [X.Y.Z]        Bump version and commit on dev branch
  promote [-b/--batch] Merge dev->main, tag, push, watch CI (-b to skip watch)
  publish [-b/--batch] Dispatch GH Actions workflow (PyPI + MCP Registry), watch by default
  run [ARGS...]       Start mcp-webgate from local source (uv run)
  query QUERY         Run webgate_query and print JSON results
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
INIT = ROOT / "src" / "mcp_webgate" / "__init__.py"
README = ROOT / "README.md"
SERVER_JSON = ROOT / "server.json"
GITHUB_REPO = "https://github.com/annibale-x/mcp-webgate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command from the project root."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=capture, text=True)


def die(msg: str) -> None:
    print(f"\n[robot] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"\n[robot] {msg}")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def read_version() -> str:
    """Read current version from pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        die("Could not find version in pyproject.toml")
    return m.group(1)


def write_version(new_ver: str) -> None:
    """Write new version into pyproject.toml and __init__.py."""
    # pyproject.toml
    text = PYPROJECT.read_text(encoding="utf-8")
    text = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        f'\\1"{new_ver}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(text, encoding="utf-8")

    # __init__.py
    if INIT.exists():
        init_text = INIT.read_text(encoding="utf-8")
        init_text = re.sub(
            r'^(__version__\s*=\s*)"[^"]+"',
            f'\\1"{new_ver}"',
            init_text,
            count=1,
            flags=re.MULTILINE,
        )
        INIT.write_text(init_text, encoding="utf-8")

    # README.md — update release badge
    if README.exists():
        readme_text = README.read_text(encoding="utf-8")
        readme_text = re.sub(
            r"(release-v)[^)]*?(-purple\.svg\))",
            f"\\g<1>{new_ver}\\2",
            readme_text,
            count=1,
        )
        readme_text = re.sub(
            r"(releases/tag/v)[^)]+\)",
            f"\\g<1>{new_ver})",
            readme_text,
            count=1,
        )
        README.write_text(readme_text, encoding="utf-8")

    # server.json — update version in root and packages
    if SERVER_JSON.exists():
        data = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
        data["version"] = new_ver
        for pkg in data.get("packages", []):
            pkg["version"] = new_ver
        SERVER_JSON.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def bump_patch(version: str) -> str:
    """Increment the patch component: X.Y.Z -> X.Y.Z+1."""
    parts = version.split(".")
    if len(parts) != 3:
        die(f"Version '{version}' is not in X.Y.Z format")
    parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


def validate_version(v: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        die(f"Version '{v}' is not in X.Y.Z format")


# ---------------------------------------------------------------------------
# Changelog helpers
# ---------------------------------------------------------------------------

def changelog_has_entry(version: str) -> bool:
    """Return True if CHANGELOG already has a section for this version."""
    text = CHANGELOG.read_text(encoding="utf-8")
    return f": v{version} -" in text


def scaffold_changelog(version: str) -> None:
    """Insert a new scaffold entry for version at the top of CHANGELOG.md."""
    today = datetime.date.today().isoformat()
    text = CHANGELOG.read_text(encoding="utf-8")

    new_entry = textwrap.dedent(f"""\
        * {today}: v{version} - TODO (Hannibal)
          * feat(): TODO

    """)

    # Insert after the "# Changelog" header line
    text = re.sub(
        r"(# Changelog\n)",
        r"\1\n" + new_entry,
        text,
        count=1,
    )

    CHANGELOG.write_text(text, encoding="utf-8")
    print(f"  Scaffolded CHANGELOG entry for v{version}")


def get_current_branch() -> str:
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_test(args: argparse.Namespace) -> None:
    info("Running test suite …")
    run(["uv", "run", "python", "-m", "pytest", "-v"])
    info("All tests passed.")


def cmd_build(args: argparse.Namespace) -> None:
    cmd_test(args)
    info("Building distribution packages …")
    import shutil
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    original_readme = inject_recent_changes(4)
    try:
        rewrite_relative_links_for_pypi()
        run(["uv", "build"])
    finally:
        restore_readme(original_readme)
    artifacts = list(dist.iterdir())
    info(f"Build complete. Artifacts in dist/:")
    for a in artifacts:
        print(f"  {a.name}")


def cmd_bump(args: argparse.Namespace) -> None:
    branch = get_current_branch()
    if branch != "dev":
        die(f"bump must run on branch 'dev' (current: '{branch}')")

    current = read_version()

    if args.version:
        new_ver = args.version
        validate_version(new_ver)
    else:
        new_ver = bump_patch(current)

    info(f"Bumping version: {current} -> {new_ver}")

    # Scaffold CHANGELOG if user hasn't already added an entry
    if not changelog_has_entry(new_ver):
        info("No CHANGELOG entry found — scaffolding …")
        scaffold_changelog(new_ver)
    else:
        info(f"CHANGELOG already has entry for {new_ver}, skipping scaffold.")

    write_version(new_ver)
    info(f"Version written to pyproject.toml, __init__.py, and server.json")

    # Commit
    files_to_add = [
        str(PYPROJECT.relative_to(ROOT)),
        str(INIT.relative_to(ROOT)),
        str(CHANGELOG.relative_to(ROOT)),
        str(README.relative_to(ROOT)),
    ]
    if SERVER_JSON.exists():
        files_to_add.append(str(SERVER_JSON.relative_to(ROOT)))
    run(["git", "add"] + files_to_add)
    run(["git", "commit", "-m", f"chore: bump version to {new_ver}"])
    run(["git", "push", "origin", "dev"])
    info(f"Committed and pushed version bump to dev.")


def cmd_promote(args: argparse.Namespace) -> None:
    branch = get_current_branch()
    if branch != "dev":
        die(f"promote must run on branch 'dev' (current: '{branch}')")

    version = read_version()
    tag = f"v{version}"

    info(f"Promoting version {version} …")

    # Check tag doesn't already exist
    result = run(["git", "tag", "-l", tag], capture=True)
    if result.stdout.strip():
        die(f"Tag '{tag}' already exists. Did you forget to bump?")

    # Build (includes test)
    cmd_build(args)

    # uv build may regenerate uv.lock — commit it if dirty before switching branches
    lock_status = run(["git", "status", "--porcelain", "uv.lock"], capture=True)
    if lock_status.stdout.strip():
        info("uv.lock was updated by build — committing before promote …")
        run(["git", "add", "uv.lock"])
        run(["git", "commit", "-m", "chore(deps): update lockfile"])

    # Merge dev -> main
    info("Merging dev -> main ...")
    run(["git", "checkout", "main"])
    run(["git", "merge", "--no-ff", "dev", "-m", f"chore: promote {tag} to main"])

    # Tag
    info(f"Tagging {tag} …")
    run(["git", "tag", "-a", tag, "-m", f"Release {tag}"])

    # Push everything
    info("Pushing dev, main, and tag …")
    run(["git", "push", "origin", "main"])
    run(["git", "push", "origin", tag])
    run(["git", "checkout", "dev"])
    run(["git", "push", "origin", "dev"])

    info(f"Promote complete. {tag} is live on main.")

    if not args.batch:
        info("Waiting for CI workflow to start …")
        import time
        time.sleep(5)
        # Find the run triggered by the tag push
        result = run(
            ["gh", "run", "list", "--workflow=ci.yml", "--limit=1", "--json=databaseId", "--jq=.[0].databaseId"],
            capture=True,
            check=False,
        )
        run_id = result.stdout.strip()
        if run_id:
            info(f"Watching CI run {run_id} …")
            ci = run(["gh", "run", "watch", run_id, "--exit-status"], check=False)
            if ci.returncode == 0:
                info("CI passed.")
            else:
                die("CI failed. Fix the issue before publishing.")
        else:
            info("Could not find CI run. Check manually: gh run list --workflow=ci.yml")


def get_version_on_branch(branch: str) -> str:
    """Read the version from pyproject.toml on a given branch."""
    try:
        result = run(["git", "show", f"{branch}:pyproject.toml"], capture=True, check=False)
        if result.returncode != 0:
            return "(branch not found)"
        m = re.search(r'^version\s*=\s*"([^"]+)"', result.stdout, re.MULTILINE)
        return m.group(1) if m else "(?)"
    except Exception:
        return "(?)"


def get_changelog_entry(version: str) -> tuple[str, str]:
    """Return (title, notes) for the given version from CHANGELOG.md."""
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = rf"(\* \d{{4}}-\d{{2}}-\d{{2}}: v{re.escape(version)} - .+?)(?=\n\* \d{{4}}|\n---|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return f"v{version}", ""
    block = m.group(1).strip()
    lines = block.splitlines()
    title_m = re.search(rf"v{re.escape(version)} - (.+?)(?:\s*\(.*\))?$", lines[0])
    title = title_m.group(1).strip() if title_m else f"v{version}"
    notes = "\n".join(lines[1:]).strip()
    return title, notes


def get_changelog_titles(n: int = 3) -> list[str]:
    """Return the first n release title lines from CHANGELOG.md."""
    try:
        text = CHANGELOG.read_text(encoding="utf-8")
        return re.findall(r"^\* \d{4}-\d{2}-\d{2}: .+", text, re.MULTILINE)[:n]
    except Exception:
        return []


def inject_recent_changes(n: int = 4) -> str:
    """Inject a Recent Changes section into README between the markers. Returns original content."""
    text = README.read_text(encoding="utf-8")
    titles = get_changelog_titles(n)
    if not titles:
        return text
    rows = "\n".join(f"| {t} |" for t in titles)
    block = (
        "<!-- RECENT_CHANGES_START -->\n"
        "## 📋 Recent Changes\n\n"
        "| Release |\n"
        "|---------|\n"
        f"{rows}\n\n"
        "<!-- RECENT_CHANGES_END -->"
    )
    patched = re.sub(
        r"<!-- RECENT_CHANGES_START -->.*?<!-- RECENT_CHANGES_END -->",
        block,
        text,
        flags=re.DOTALL,
    )
    README.write_text(patched, encoding="utf-8")
    return text


def restore_readme(original: str) -> None:
    README.write_text(original, encoding="utf-8")


def rewrite_relative_links_for_pypi() -> None:
    """Rewrite relative Markdown links to absolute GitHub URLs (in-place).

    Relative links are valid on GitHub but broken on PyPI, which renders the
    README as a standalone page with no knowledge of the repository layout.
    """
    text = README.read_text(encoding="utf-8")

    def _abs(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        # Leave absolute URLs, anchor-only links, and mailto untouched
        if re.match(r"^https?://", href) or href.startswith("#") or href.startswith("mailto:"):
            return m.group(0)
        # Split path and optional anchor (#section)
        path, anchor = (href.split("#", 1) + [""])[:2]
        anchor = ("#" + anchor) if anchor else ""
        # Directory links → /tree/; file links → /blob/
        if path.endswith("/"):
            abs_url = f"{GITHUB_REPO}/tree/main/{path.rstrip('/')}"
        else:
            abs_url = f"{GITHUB_REPO}/blob/main/{path}"
        return f"[{label}]({abs_url}{anchor})"

    patched = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _abs, text)
    README.write_text(patched, encoding="utf-8")


def count_tests() -> int:
    """Count test functions in the tests/ directory."""
    tests_dir = ROOT / "tests"
    total = 0
    for f in tests_dir.glob("test_*.py"):
        text = f.read_text(encoding="utf-8")
        total += len(re.findall(r"^\s+(?:async )?def test_", text, re.MULTILINE))
    return total


def cmd_status(args: argparse.Namespace) -> None:
    branch = get_current_branch()
    dev_ver = get_version_on_branch("dev")
    main_ver = get_version_on_branch("main")
    titles = get_changelog_titles(3)
    n_tests = count_tests()

    # Uncommitted changes
    dirty = run(["git", "status", "--porcelain"], capture=True, check=False)
    dirty_count = len([l for l in dirty.stdout.splitlines() if l.strip()])

    print()
    print("=" * 52)
    print("  mcp-webgate project status")
    print("=" * 52)
    print(f"  branch   : {branch}")
    print(f"  dev      : v{dev_ver}")
    print(f"  main     : v{main_ver}")
    print(f"  tests    : {n_tests} collected")
    print(f"  dirty    : {dirty_count} uncommitted file(s)")
    print()
    print("  Recent releases:")
    for t in titles:
        print(f"    {t}")
    print("=" * 52)


def cmd_install(args: argparse.Namespace) -> None:
    """Uninstall mcp-webgate tool, clean cache, rebuild, and install fresh."""
    version = read_version()

    info("Uninstalling mcp-webgate tool …")
    run(["uv", "tool", "uninstall", "mcp-webgate"], check=False)

    info("Clearing cached tool environments …")
    run(["uv", "cache", "prune"], check=False)

    # Build fresh wheel
    cmd_build(args)

    # Find and install the wheel
    dist = ROOT / "dist"
    wheels = list(dist.glob("*.whl"))
    if not wheels:
        die("No wheel found in dist/")

    whl = wheels[0]
    info(f"Installing {whl.name} …")
    run(["uv", "tool", "install", str(whl)])

    info(f"mcp-webgate v{version} installed as uv tool.")


def cmd_run(args: argparse.Namespace) -> None:
    """Start the MCP server from local source via uv run."""
    cmd = ["uv", "run", "mcp-webgate"] + args.extra
    info("Starting mcp-webgate from local source …")
    run(cmd, check=False)


def cmd_query(args: argparse.Namespace) -> None:
    """Execute a webgate_query using the local config and print results as JSON."""
    import asyncio
    import json as _json
    import sys as _sys

    src = ROOT / "src"
    if str(src) not in _sys.path:
        _sys.path.insert(0, str(src))

    from mcp_webgate.config import load_config  # noqa: PLC0415
    from mcp_webgate.tools.query import tool_query  # noqa: PLC0415

    cfg = load_config()
    backend_name = args.backend or cfg.backends.default

    if backend_name == "searxng":
        from mcp_webgate.backends.searxng import SearxngBackend  # noqa: PLC0415
        backend = SearxngBackend(cfg.backends.searxng)
    elif backend_name == "brave":
        from mcp_webgate.backends.brave import BraveBackend  # noqa: PLC0415
        backend = BraveBackend(cfg.backends.brave)
    elif backend_name == "tavily":
        from mcp_webgate.backends.tavily import TavilyBackend  # noqa: PLC0415
        backend = TavilyBackend(cfg.backends.tavily)
    elif backend_name == "exa":
        from mcp_webgate.backends.exa import ExaBackend  # noqa: PLC0415
        backend = ExaBackend(cfg.backends.exa)
    elif backend_name == "serpapi":
        from mcp_webgate.backends.serpapi import SerpapiBackend  # noqa: PLC0415
        backend = SerpapiBackend(cfg.backends.serpapi)
    else:
        die(f"Unknown backend: {backend_name!r}")

    trace = True  # robot query is a dev tool — always include trace data

    info(f"Querying {args.query!r} via {backend_name} …")
    result = asyncio.run(tool_query(
        args.query,
        backend,
        cfg,
        num_results_per_query=args.num_results,
        lang=args.lang,
        trace=trace,
    ))
    print(_json.dumps(result, ensure_ascii=False, indent=2))


def _create_github_release(version: str, tag: str) -> None:
    """Create a GitHub Release from the CHANGELOG entry (idempotent)."""
    # Skip if release already exists
    check = run(["gh", "release", "view", tag], capture=True, check=False)
    if check.returncode == 0:
        info(f"GitHub Release {tag} already exists, skipping.")
        return

    title, notes = get_changelog_entry(version)
    info(f"Creating GitHub Release {tag} …")
    cmd = ["gh", "release", "create", tag, "--title", f"{tag} - {title}", "--target", "main"]
    if notes:
        cmd += ["--notes", notes]
    else:
        cmd += ["--generate-notes"]
    result = run(cmd, check=False)
    if result.returncode == 0:
        info(f"GitHub Release {tag} created.")
    else:
        info(f"Could not create GitHub Release. Create manually: gh release create {tag}")


def cmd_publish(args: argparse.Namespace) -> None:
    version = read_version()
    tag = f"v{version}"

    # Verify the tag exists (promote must have run first)
    result = run(["git", "tag", "-l", tag], capture=True)
    if not result.stdout.strip():
        die(f"Tag '{tag}' not found. Run 'robot promote' first.")

    info(f"Dispatching publish workflow for {tag} …")
    run(["gh", "workflow", "run", "publish.yml", "--ref", "main"])

    if not args.batch:
        import time
        time.sleep(5)
        result = run(
            ["gh", "run", "list", "--workflow=publish.yml", "--limit=1", "--json=databaseId", "--jq=.[0].databaseId"],
            capture=True,
            check=False,
        )
        run_id = result.stdout.strip()
        if run_id:
            info(f"Watching publish run {run_id} …")
            pub = run(["gh", "run", "watch", run_id, "--exit-status"], check=False)
            if pub.returncode == 0:
                info("Publish complete.")
                _create_github_release(version, tag)
            else:
                die("Publish workflow failed. Check: gh run view --log-failed")
        else:
            info("Could not find publish run. Check: gh run list --workflow=publish.yml")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="robot",
        description="Project automation for mcp-webgate",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("test", help="Run the full test suite")
    sub.add_parser("build", help="Build PyPI wheel + sdist into dist/")

    p_bump = sub.add_parser("bump", help="Bump version and commit on dev")
    p_bump.add_argument(
        "version",
        nargs="?",
        metavar="X.Y.Z",
        help="Target version (default: auto-increment patch)",
    )

    sub.add_parser("status", help="Show branch, versions, recent changelog, test count")
    sub.add_parser("install", help="Uninstall, clean, rebuild, and install as uv tool")
    p_promote = sub.add_parser("promote", help="Merge dev->main, tag, push, watch CI")
    p_promote.add_argument(
        "-b", "--batch",
        action="store_true",
        help="Skip CI watch (for scripting)",
    )

    p_run = sub.add_parser("run", help="Start mcp-webgate from local source (uv run)")
    p_run.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        metavar="ARGS",
        help="Extra args forwarded to mcp-webgate (e.g. --debug --llm-enabled)",
    )

    p_pub = sub.add_parser("publish", help="Dispatch GitHub Actions publish workflow (PyPI + MCP Registry)")
    p_pub.add_argument(
        "-b", "--batch",
        action="store_true",
        help="Skip workflow watch (for scripting)",
    )

    p_query = sub.add_parser("query", help="Run webgate_query and print JSON results")
    p_query.add_argument("query", metavar="QUERY", help="Search query string")
    p_query.add_argument(
        "-n", "--num-results",
        dest="num_results",
        type=int,
        default=5,
        metavar="N",
        help="Results per query (default: 5)",
    )
    p_query.add_argument(
        "-l", "--lang",
        default=None,
        metavar="LANG",
        help="Language code, e.g. en, it (default: none)",
    )
    p_query.add_argument(
        "-b", "--backend",
        default=None,
        metavar="BACKEND",
        help="Backend to use: searxng|brave|tavily|exa|serpapi (default: config value)",
    )

    # parse_known_args to allow passthrough flags for the 'run' subcommand.
    # For all other commands, unknown args are treated as an error.
    args, extra = parser.parse_known_args()
    if extra and args.command != "run":
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.extra = extra

    dispatch = {
        "test": cmd_test,
        "build": cmd_build,
        "bump": cmd_bump,
        "install": cmd_install,
        "run": cmd_run,
        "status": cmd_status,
        "promote": cmd_promote,
        "publish": cmd_publish,
        "query": cmd_query,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
