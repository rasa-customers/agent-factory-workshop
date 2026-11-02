"""`workshop` command: doctor | up | checkpoint."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from workshop.env import check_settings, load_settings


def doctor() -> int:
    problems = []
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        problems.append(f"Python 3.11–3.13 is required (you have {sys.version.split()[0]}). On Windows, use WSL.")
    problems += check_settings(load_settings())
    rasa = shutil.which("rasa")
    if not rasa or subprocess.run([rasa, "--version"], capture_output=True).returncode != 0:
        problems.append("`rasa` is not runnable — re-run ./setup.sh.")
    if problems:
        print("Workshop doctor found problems:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("✓ Everything looks good. Next: workshop up")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workshop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check your setup")
    sub.add_parser("up", help="start the factory, foreman and tools")
    cp = sub.add_parser("checkpoint", help="jump to a known-good build")
    cp.add_argument("name")
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return doctor()
    from workshop import procs  # wired in Task 9

    if args.cmd == "up":
        return procs.up()
    return procs.checkpoint(args.name)


if __name__ == "__main__":
    sys.exit(main())
