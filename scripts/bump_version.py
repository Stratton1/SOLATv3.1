#!/usr/bin/env python3
"""
Version bump script for SOLAT v3.1.

Updates version in all locations:
- engine/pyproject.toml
- engine/solat_engine/__init__.py
- apps/desktop/package.json
- apps/desktop/src-tauri/tauri.conf.json
- package.json (root)

Usage:
    python scripts/bump_version.py patch   # 3.1.0 -> 3.1.1
    python scripts/bump_version.py minor   # 3.1.0 -> 3.2.0
    python scripts/bump_version.py major   # 3.1.0 -> 4.0.0
    python scripts/bump_version.py 3.2.1   # Set specific version
    python scripts/bump_version.py --check # Show current version
"""

import json
import re
import sys
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).parent.parent

# Version file locations
VERSION_FILES = {
    "pyproject.toml": PROJECT_ROOT / "engine" / "pyproject.toml",
    "__init__.py": PROJECT_ROOT / "engine" / "solat_engine" / "__init__.py",
    "desktop/package.json": PROJECT_ROOT / "apps" / "desktop" / "package.json",
    "tauri.conf.json": PROJECT_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json",
    "root/package.json": PROJECT_ROOT / "package.json",
}


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse version string into (major, minor, patch)."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple as string."""
    return f"{major}.{minor}.{patch}"


def get_current_version() -> str:
    """Get current version from pyproject.toml (authoritative source)."""
    pyproject_path = VERSION_FILES["pyproject.toml"]
    content = pyproject_path.read_text()

    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find version in pyproject.toml")

    return match.group(1)


def bump_version(current: str, bump_type: str) -> str:
    """Calculate new version based on bump type."""
    major, minor, patch = parse_version(current)

    if bump_type == "patch":
        return format_version(major, minor, patch + 1)
    elif bump_type == "minor":
        return format_version(major, minor + 1, 0)
    elif bump_type == "major":
        return format_version(major + 1, 0, 0)
    else:
        # Assume it's a specific version
        parse_version(bump_type)  # Validate format
        return bump_type


def update_pyproject_toml(path: Path, new_version: str) -> None:
    """Update version in pyproject.toml."""
    content = path.read_text()
    updated = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        f'\\1"{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    path.write_text(updated)


def update_init_py(path: Path, new_version: str) -> None:
    """Update __version__ in __init__.py."""
    content = path.read_text()
    updated = re.sub(
        r'^(__version__\s*=\s*)"[^"]+"',
        f'\\1"{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    path.write_text(updated)


def update_package_json(path: Path, new_version: str) -> None:
    """Update version in package.json."""
    content = json.loads(path.read_text())
    content["version"] = new_version
    path.write_text(json.dumps(content, indent=2) + "\n")


def update_tauri_conf_json(path: Path, new_version: str) -> None:
    """Update version in tauri.conf.json."""
    content = json.loads(path.read_text())
    content["version"] = new_version
    path.write_text(json.dumps(content, indent=2) + "\n")


def update_all_versions(new_version: str) -> None:
    """Update version in all files."""
    print(f"Updating to version {new_version}...")

    # Update each file
    update_pyproject_toml(VERSION_FILES["pyproject.toml"], new_version)
    print(f"  Updated: engine/pyproject.toml")

    update_init_py(VERSION_FILES["__init__.py"], new_version)
    print(f"  Updated: engine/solat_engine/__init__.py")

    update_package_json(VERSION_FILES["desktop/package.json"], new_version)
    print(f"  Updated: apps/desktop/package.json")

    update_tauri_conf_json(VERSION_FILES["tauri.conf.json"], new_version)
    print(f"  Updated: apps/desktop/src-tauri/tauri.conf.json")

    update_package_json(VERSION_FILES["root/package.json"], new_version)
    print(f"  Updated: package.json (root)")

    print(f"\nVersion updated to {new_version} in all locations.")


def check_version_sync() -> bool:
    """Check if all version files are in sync."""
    versions: dict[str, str] = {}

    # pyproject.toml
    content = VERSION_FILES["pyproject.toml"].read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    versions["pyproject.toml"] = match.group(1) if match else "NOT FOUND"

    # __init__.py
    content = VERSION_FILES["__init__.py"].read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    versions["__init__.py"] = match.group(1) if match else "NOT FOUND"

    # package.json files
    for key in ["desktop/package.json", "root/package.json"]:
        content = json.loads(VERSION_FILES[key].read_text())
        versions[key] = content.get("version", "NOT FOUND")

    # tauri.conf.json
    content = json.loads(VERSION_FILES["tauri.conf.json"].read_text())
    versions["tauri.conf.json"] = content.get("version", "NOT FOUND")

    # Print status
    print("Version status:")
    unique_versions = set(versions.values())
    in_sync = len(unique_versions) == 1

    for name, version in versions.items():
        status = "OK" if in_sync else ("MISMATCH" if version != list(unique_versions)[0] else "")
        print(f"  {name}: {version} {status}")

    if in_sync:
        print(f"\nAll versions in sync: {list(unique_versions)[0]}")
    else:
        print(f"\nWARNING: Versions are out of sync!")

    return in_sync


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    command = sys.argv[1]

    if command == "--check":
        check_version_sync()
        return 0

    if command == "--help" or command == "-h":
        print(__doc__)
        return 0

    # Get current version
    current = get_current_version()
    print(f"Current version: {current}")

    # Calculate new version
    try:
        new_version = bump_version(current, command)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Confirm if not same
    if new_version == current:
        print("No version change.")
        return 0

    # Update all files
    update_all_versions(new_version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
