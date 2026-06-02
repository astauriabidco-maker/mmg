#!/usr/bin/env python3
"""Backup or restore the SQLite database used by MMG."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def backup(source: Path, target_dir: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target


def restore(source: Path, target: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup or restore an MMG SQLite database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--source", default="./atelier.db")
    backup_parser.add_argument("--target-dir", default="./backups")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--source", required=True)
    restore_parser.add_argument("--target", default="./atelier.db")

    args = parser.parse_args()
    if args.command == "backup":
        path = backup(Path(args.source), Path(args.target_dir))
        print(path)
    else:
        path = restore(Path(args.source), Path(args.target))
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
