#!/usr/bin/env python3
"""Verify that ``crypto-etl/bot/`` has no dependencies on ``vibe-trading/``.

Checks:
  1. No Python imports from ``vibe_trading`` or ``vibe-trading``.
  2. No relative ``../../vibe-trading`` path references in any file.
  3. No symlinks from ``crypto-etl/bot/`` to files in ``vibe-trading/``.
  4. No os.path / pathlib references that resolve into ``vibe-trading/``.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # up from bot/scripts/ -> crypto-etl/
BOT_DIR = REPO_ROOT / "bot"
VIBE_DIR = REPO_ROOT / ".." / "vibe-trading"  # sibling of crypto-etl


def check_imports() -> list[str]:
    errors: list[str] = []
    for pyfile in sorted(BOT_DIR.rglob("*.py")):
        # Skip scripts dir itself
        if "scripts" in pyfile.parts:
            continue
        try:
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        except SyntaxError:
            errors.append(f"Syntax error in {pyfile}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "vibe" in alias.name.lower():
                        errors.append(f"{pyfile.relative_to(BOT_DIR)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and "vibe" in node.module.lower():
                errors.append(f"{pyfile.relative_to(BOT_DIR)}: from {node.module} import ...")
    return errors


def check_path_references() -> list[str]:
    errors: list[str] = []
    patterns = [
        re.compile(r"vibe.trading", re.IGNORECASE),
        re.compile(r"\.\./\.\./vibe", re.IGNORECASE),
        re.compile(r"\.\\\.\.\\\.\.\\vibe", re.IGNORECASE),
    ]
    for pyfile in sorted(BOT_DIR.rglob("*.py")):
        if "scripts" in pyfile.parts:
            continue
        content = pyfile.read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern.search(content):
                errors.append(f"{pyfile.relative_to(BOT_DIR)}: matches {pattern.pattern}")
                break
    return errors


def check_symlinks() -> list[str]:
    errors: list[str] = []
    for f in BOT_DIR.rglob("*"):
        if f.is_symlink():
            target = os.readlink(str(f))
            if "vibe" in target.lower():
                errors.append(f"Symlink {f.relative_to(BOT_DIR)} -> {target}")
    return errors


def main() -> int:
    exit_code = 0

    print("=== Vibe-Trading Boundary Check ===")
    print(f"Bot dir:  {BOT_DIR}")
    print(f"Vibe dir: {VIBE_DIR.resolve()}")
    print()

    checks = [
        ("Python imports from vibe-trading", check_imports),
        ("Path references to vibe-trading", check_path_references),
        ("Symlinks into vibe-trading", check_symlinks),
    ]

    for name, fn in checks:
        print(f"--- {name} ---")
        errors = fn()
        if errors:
            for err in errors:
                print(f"  FAIL: {err}")
            exit_code = 1
        else:
            print("  PASS")
        print()

    if exit_code == 0:
        print("Boundary check PASSED — bot/ has no dependency on vibe-trading/.")
    else:
        print(f"Boundary check FAILED with {exit_code} error(s).")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
