"""Nuitka build configuration — constructs and runs the compilation command."""

import os
import subprocess
import sys

INCLUDE_PACKAGES = [
    "playwright", "openai", "rich", "playwright_stealth",
    "qrcode", "certifi", "httpx", "httpcore", "anyio", "sniffio",
    "h11", "pydantic", "tqdm", "greenlet", "pyee", "typer",
    "img2pdf", "yaml", "onepassword", "click",
]


def build_nuitka_command() -> list[str]:
    """Build Nuitka command line arguments."""
    entry_dir = os.environ.get("NUITKA_INPUT_DIR", "src")
    entry_point = f"{entry_dir}/main.py"

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--output-dir=dist",
        "--output-filename=ykt",
    ]

    for pkg in INCLUDE_PACKAGES:
        cmd.append(f"--include-package={pkg}")

    cmd.append(f"--jobs={os.cpu_count()}")
    cmd.append("--nofollow-import-to=onepassword.test_client")
    cmd.append("--python-flag=no_docstrings")
    cmd.append("--remove-output")
    cmd.append("--assume-yes-for-downloads")

    if sys.platform == "win32":
        cmd.append("--msvc=latest")
        cmd.append("--windows-console-mode=attach")

    cmd.append(entry_point)
    return cmd


def main() -> None:
    """Print the Nuitka command and execute it."""
    cmd = build_nuitka_command()
    entry_point = cmd[-1]
    if not os.path.isfile(entry_point):
        print(f"Error: Entry point not found: {entry_point}", file=sys.stderr)
        print("Ensure previous build stages completed successfully.", file=sys.stderr)
        sys.exit(1)
    print(" ".join(cmd))
    try:
        result = subprocess.run(cmd)
    except FileNotFoundError:
        print("Error: Nuitka is not installed. Install with: pip install nuitka", file=sys.stderr)
        sys.exit(1)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
