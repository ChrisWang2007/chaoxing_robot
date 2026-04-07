#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a one-file EXE and prepare a desktop release folder.

Key guarantees:
- Entry point is mooc_robot.py
- Browser drivers are NOT bundled into the EXE
- page_address.txt / page_cookie.txt / api.txt are NOT bundled into the EXE
- Drivers and config files are copied next to the EXE in a desktop release folder
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = 'mooc_robot'
PROJECT_DIR = Path(__file__).resolve().parent
SPEC_PATH = PROJECT_DIR / f'{APP_NAME}.spec'
DIST_DIR = PROJECT_DIR / 'dist_release'
BUILD_DIR = PROJECT_DIR / 'build_release'
RELEASE_DIR = Path.home() / 'Desktop' / 'mooc_robot_release'

CONFIG_FILES = [
    'page_address.txt',
    'page_cookie.txt',
    'api.txt',
]

DRIVER_FILES = [
    'edgeDriver.exe',
    'chromeDriver.exe',
    'firefoxDriver.exe',
    'ieDriverServer.exe',
]

EXTERNAL_FILES = CONFIG_FILES + DRIVER_FILES


def status(prefix: str, message: str) -> None:
    print(f'{prefix} {message}')


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        status('[OK]', 'PyInstaller is installed.')
    except ImportError:
        status('[...]', 'PyInstaller is missing, installing now...')
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
            check=True,
            cwd=PROJECT_DIR,
        )
        status('[OK]', 'PyInstaller installation completed.')


def require_files(paths: list[Path], label: str) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        joined = '\n'.join(missing)
        raise FileNotFoundError(f'Missing {label}:\n{joined}')


def clean_path(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def build_exe() -> Path:
    ensure_pyinstaller()
    require_files([PROJECT_DIR / 'mooc_robot.py', SPEC_PATH], 'entry file or spec file')

    status('[...]', 'Cleaning previous build folders...')
    clean_path(DIST_DIR)
    clean_path(BUILD_DIR)

    command = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--distpath',
        str(DIST_DIR),
        '--workpath',
        str(BUILD_DIR),
        str(SPEC_PATH),
    ]

    status('[...]', 'Running PyInstaller...')
    subprocess.run(command, check=True, cwd=PROJECT_DIR)

    exe_path = DIST_DIR / f'{APP_NAME}.exe'
    if not exe_path.exists():
        raise FileNotFoundError(f'Build finished but EXE was not found: {exe_path}')

    status('[OK]', f'EXE build completed: {exe_path}')
    return exe_path


def prepare_release_folder(exe_path: Path) -> Path:
    source_paths = [PROJECT_DIR / filename for filename in EXTERNAL_FILES]
    require_files(source_paths, 'external config or driver files')

    status('[...]', f'Preparing desktop release folder: {RELEASE_DIR}')
    clean_path(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe_path, RELEASE_DIR / exe_path.name)
    status('[OK]', f'Copied EXE: {RELEASE_DIR / exe_path.name}')

    for filename in EXTERNAL_FILES:
        source = PROJECT_DIR / filename
        target = RELEASE_DIR / filename
        shutil.copy2(source, target)
        status('[OK]', f'Copied external file: {filename}')

    return RELEASE_DIR


def print_release_summary(exe_path: Path, release_dir: Path) -> None:
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    status('[INFO]', f'EXE size: {size_mb:.1f} MB')
    status('[INFO]', f'Desktop release folder: {release_dir}')
    status('[INFO]', 'Folder contents:')
    for item in sorted(release_dir.iterdir(), key=lambda path: path.name.lower()):
        kind = 'DIR ' if item.is_dir() else 'FILE'
        print(f'  - [{kind}] {item.name}')


def main() -> int:
    try:
        exe_path = build_exe()
        release_dir = prepare_release_folder(exe_path)
        print_release_summary(exe_path, release_dir)
        status('[OK]', 'Desktop EXE release folder is ready.')
        return 0
    except Exception as exc:
        status('[ERR]', f'Packaging failed: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
