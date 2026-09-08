from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = "mavis.db"
DATA_DIRS = ("repository", "library")
ENV_FILE = ".env"
BACKUP_DIR = ROOT / "upgrade_backups"


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def portable_manifest(source: Path) -> dict:
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_folder": str(source),
        "includes": [DATA_FILE, *DATA_DIRS],
        "excludes": [ENV_FILE],
        "note": ".env is intentionally excluded from backup ZIPs because it may contain API keys.",
    }


def make_backup(source: Path = ROOT) -> Path:
    source = source.resolve()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"Mavis-Campus-Data-Backup-{stamp()}.zip"
    manifest = portable_manifest(source)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        db_path = source / DATA_FILE
        if db_path.is_file():
            zf.write(db_path, DATA_FILE)
        for dirname in DATA_DIRS:
            root = source / dirname
            if root.is_dir():
                wrote = False
                for file in sorted(root.rglob("*")):
                    if file.is_file():
                        zf.write(file, file.relative_to(source).as_posix())
                        wrote = True
                if not wrote:
                    zf.writestr(f"{dirname}/.keep", "")
        zf.writestr("backup-manifest.json", json.dumps(manifest, indent=2))
    return out


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"Unsafe path in backup: {member.filename}")
        target = (dest / name).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"Unsafe path in backup: {member.filename}")
    zf.extractall(dest)


def restore_backup(backup: Path, target: Path = ROOT) -> None:
    backup = backup.expanduser().resolve()
    target = target.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"Backup not found: {backup}")
    pre = make_backup(target)
    temp = target / f".upgrade-restore-{stamp()}"
    temp.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(backup, "r") as zf:
            _safe_extract(zf, temp)
        src_db = temp / DATA_FILE
        if src_db.is_file():
            shutil.copy2(src_db, target / DATA_FILE)
        for dirname in DATA_DIRS:
            src = temp / dirname
            if src.is_dir():
                dst = target / dirname
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".keep"))
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    print(f"Pre-restore safety backup: {pre}")


def import_previous(source: Path, target: Path = ROOT) -> None:
    source = source.expanduser().resolve()
    target = target.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Previous Campus folder not found: {source}")
    if source == target:
        raise ValueError("Choose the previous Campus version folder, not this new folder.")
    if not (source / DATA_FILE).is_file():
        raise FileNotFoundError(f"No {DATA_FILE} found in previous Campus folder: {source}")
    pre = make_backup(target)
    shutil.copy2(source / DATA_FILE, target / DATA_FILE)
    env = source / ENV_FILE
    if env.is_file():
        shutil.copy2(env, target / ENV_FILE)
    for dirname in DATA_DIRS:
        src = source / dirname
        if not src.is_dir():
            continue
        dst = target / dirname
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    print(f"Imported Campus data from: {source}")
    print(f"Safety backup of this folder before import: {pre}")
    if not env.is_file():
        print("No .env was present in the previous folder; configure .env separately if needed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mavis Digital Campus upgrade helper")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup", help="Create a portable data backup ZIP (excludes .env).")
    restore = sub.add_parser("restore", help="Restore a portable data backup ZIP into this Campus folder.")
    restore.add_argument("backup")
    imp = sub.add_parser("import-folder", help="Copy local data from a previous Campus version folder.")
    imp.add_argument("source")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            out = make_backup(ROOT)
            print(f"Upgrade backup created: {out}")
            print("IMPORTANT: .env is not inside the ZIP. Keep your .env separately.")
        elif args.command == "restore":
            restore_backup(Path(args.backup), ROOT)
            print("Backup restored. Start the Campus normally; database upgrades run automatically.")
        elif args.command == "import-folder":
            import_previous(Path(args.source), ROOT)
            print("Import complete. Start the new Campus normally.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
