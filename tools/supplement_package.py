#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/hao/Documents/自助报销Agent")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_reimbursement_package import OUTPUT_ROOT, build_package, export_package  # noqa: E402

WORK_ROOT = ROOT / "data/package_work"


def package_dir(package: str) -> Path:
    path = Path(package)
    if path.exists() and path.is_dir():
        return path
    return OUTPUT_ROOT / package


def load_package(directory: Path) -> dict:
    package_json = directory / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"Package not found: {directory}")
    return json.loads(package_json.read_text(encoding="utf-8"))


def archive_package(directory: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = directory / "versions" / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "package.json",
        "package.md",
        "playwright_plan.json",
        "return_diagnosis.json",
        "return_diagnosis.md",
    ]:
        src = directory / name
        if src.exists():
            shutil.copy2(src, archive_dir / name)
    files_dir = directory / "files"
    if files_dir.exists():
        shutil.copytree(files_dir, archive_dir / "files", dirs_exist_ok=True)
    return archive_dir


def rebuild_with_supplements(directory: Path, supplements: list[Path], note: str = "") -> dict:
    package = load_package(directory)
    archive_dir = archive_package(directory)

    work_dir = WORK_ROOT / f"{directory.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    work_dir.mkdir(parents=True, exist_ok=True)
    existing_files = directory / "files"
    if existing_files.exists():
        for src in existing_files.iterdir():
            if src.is_file():
                shutil.copy2(src, work_dir / src.name)
    for src in supplements:
        if src.exists() and src.is_file():
            target = work_dir / src.name
            if target.exists():
                target = work_dir / f"supplement-{src.name}"
            shutil.copy2(src, target)

    merged_note = package.get("user_note", "")
    if note:
        merged_note = f"{merged_note}\n补充说明：{note}".strip()
    new_package = build_package(work_dir, merged_note, package["title"])
    export_package(new_package, directory)
    return {
        "package": str(directory),
        "archive": str(archive_dir),
        "work_dir": str(work_dir),
        "missing_required": [item.name for item in new_package.checklist if item.status == "missing"],
        "documents": [doc.file_name for doc in new_package.documents],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Supplement an existing reimbursement package with additional files and rebuild it.")
    parser.add_argument("package", help="Package id or package directory")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    result = rebuild_with_supplements(package_dir(args.package), args.files, args.note)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
