#!/usr/bin/env python3
"""
robot.py — Project automation for mcp-xsearch.

Commands:
  test                Run the full test suite
  build               Build PyPI wheel + sdist into dist/
  bump [X.Y.Z]        Bump version and commit on dev branch
  promote             Merge dev->main, tag, push, checkout dev
  publish [-t/--test] Publish to PyPI (or TestPyPI with -t/--test)
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
INIT = ROOT / "src" / "mcp_xsearch" / "__init__.py"


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
    return f"## [{version}]" in text


def scaffold_changelog(version: str) -> None:
    """Insert a new section for version into CHANGELOG.md."""
    today = datetime.date.today().isoformat()
    text = CHANGELOG.read_text(encoding="utf-8")

    new_section = textwrap.dedent(f"""\
        ## [{version}] - {today}

        ### Added
        -

        ### Changed
        -

        ### Fixed
        -

    """)

    # Insert after the ## [Unreleased] header (or at the top of releases)
    text = re.sub(
        r"(## \[Unreleased\].*?\n)",
        r"\1\n" + new_section,
        text,
        count=1,
        flags=re.DOTALL,
    )

    # Add link reference at the bottom
    prev_ver = read_version()  # current version before bump
    old_link = f"[{prev_ver}]: https://github.com/annibale-x/mcp-xsearch/releases/tag/v{prev_ver}"
    new_link = (
        f"[{version}]: https://github.com/annibale-x/mcp-xsearch/compare/v{prev_ver}...v{version}\n"
        + old_link
    )
    text = text.replace(old_link, new_link)

    CHANGELOG.write_text(text, encoding="utf-8")
    print(f"  Scaffolded CHANGELOG entry for {version}")


def get_current_branch() -> str:
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_test(args: argparse.Namespace) -> None:
    info("Running test suite …")
    run(["uv", "run", "pytest", "-v"])
    info("All tests passed.")


def cmd_build(args: argparse.Namespace) -> None:
    info("Building distribution packages …")
    import shutil
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    run(["uv", "build"])
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

    info(f"Bumping version: {current} → {new_ver}")

    # Scaffold CHANGELOG if user hasn't already added an entry
    if not changelog_has_entry(new_ver):
        info("No CHANGELOG entry found — scaffolding …")
        scaffold_changelog(new_ver)
    else:
        info(f"CHANGELOG already has entry for {new_ver}, skipping scaffold.")

    write_version(new_ver)
    info(f"Version written to pyproject.toml and __init__.py")

    # Commit
    run(["git", "add",
         str(PYPROJECT.relative_to(ROOT)),
         str(INIT.relative_to(ROOT)),
         str(CHANGELOG.relative_to(ROOT))])
    run(["git", "commit", "-m", f"chore: bump version to {new_ver}"])
    info(f"Committed version bump to dev.")


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

    # Merge dev -> main
    info("Merging dev → main …")
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


def cmd_publish(args: argparse.Namespace) -> None:
    dist = ROOT / "dist"
    if not dist.exists() or not list(dist.iterdir()):
        die("dist/ is empty. Run 'python scripts/robot.py build' first.")

    if args.test:
        info("Publishing to TestPyPI …")
        run(["uv", "publish", "--publish-url", "https://test.pypi.org/legacy/"])
    else:
        info("Publishing to PyPI …")
        run(["uv", "publish"])

    info("Publish complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="robot",
        description="Project automation for mcp-xsearch",
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

    sub.add_parser("promote", help="Merge dev→main, tag, push, checkout dev")

    p_pub = sub.add_parser("publish", help="Publish to PyPI")
    p_pub.add_argument(
        "-t", "--test",
        action="store_true",
        help="Publish to TestPyPI instead",
    )

    args = parser.parse_args()

    dispatch = {
        "test": cmd_test,
        "build": cmd_build,
        "bump": cmd_bump,
        "promote": cmd_promote,
        "publish": cmd_publish,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
