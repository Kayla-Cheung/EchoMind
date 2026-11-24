"""Copy an explicitly selected human reference; never overwrite different raw data."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def copy_reference(source, destination):
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Source must be a file")
    expected = sha256(source)
    if destination.exists():
        if not destination.is_file() or sha256(destination) != expected:
            raise ValueError("A different raw reference exists; existing data was preserved")
        return "unchanged", expected
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation refuses a destination created after the existence check.
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
    if sha256(destination) != expected:
        raise ValueError("Copy hash mismatch; inspect the source and new copy before analysis")
    return "copied", expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Permitted source CSV, explicitly selected")
    args = parser.parse_args(argv)
    destination = Path(__file__).resolve().parent / "data/raw/rr.csv"
    try:
        status, fingerprint = copy_reference(args.source, destination)
    except (OSError, ValueError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    print(f"Reference {status}; SHA256: {fingerprint}")
    print(f"Destination: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
