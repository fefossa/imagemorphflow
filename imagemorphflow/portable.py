"""Filesystem and executable helpers for Windows, macOS and Linux."""

import csv
import errno
import logging
import os
import shutil
import uuid
from pathlib import Path


SYMLINK_PERMISSION_ERRORS = {errno.EPERM, errno.EACCES, errno.ENOTSUP}


def symlink_unavailable(error):
    return error.errno in SYMLINK_PERMISSION_ERRORS or getattr(error, "winerror", None) == 1314


def image_directory(source, destination, mode="auto"):
    """Return a usable image directory, optionally creating a directory symlink.

    Auto/reference modes never copy microscopy datasets. Existing real folders
    are preserved; auto mode can read the source directly instead.
    """
    if mode not in ("auto", "symlink", "reference"):
        raise ValueError("image_link_mode must be auto, symlink or reference")
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_dir():
        raise FileNotFoundError(f"Image directory missing: {source}")
    if mode == "reference" or source == destination:
        return source
    # Do not place a link inside its own target tree.
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError(f"Image link would be inside its source: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source:
            return destination
        destination.unlink()
    elif destination.exists():
        if mode == "auto" and destination.is_dir():
            logging.info("Preserving existing image folder; reading source directly: %s", source)
            return source
        raise FileExistsError(f"Refusing to replace existing path: {destination}")
    try:
        destination.symlink_to(source, target_is_directory=True)
        return destination
    except OSError as error:
        if mode != "auto" or not symlink_unavailable(error):
            raise
        logging.info("Directory symlinks unavailable; reading images directly from %s", source)
        return source


def latest_config(source, destination):
    """Use a small atomic file copy when config symlinks are unavailable."""
    source, destination = Path(source), Path(destination)
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        try:
            temporary.symlink_to(source.name)
        except OSError as error:
            if not symlink_unavailable(error):
                raise
            shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()


def plate_image_directory(config, plate):
    """Read the actual directory recorded by load_data, including reference mode."""
    csv_path = Path(config["base_path"]) / "loaddata" / plate / "load_data.csv"
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as stream:
            row = next(csv.DictReader(stream), {})
        for key, value in row.items():
            if key.startswith("PathName_") and not key.startswith("PathName_Illum") and value:
                return Path(value)
    return Path(config["image_local_path"].format(plate_new=plate))


def conda_command(environment, arguments, executable=None):
    """Prefer the real Conda executable, including CONDA_EXE on Windows."""
    command = executable or os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
    if str(command).lower().endswith((".bat", ".cmd")):
        candidate = Path(command).parent.parent / "Scripts" / "conda.exe"
        if candidate.is_file():
            command = str(candidate)
        else:
            raise ValueError("Set conda_executable or CONDA_EXE to the actual conda.exe, not a .bat/.cmd wrapper")
    return [str(command), "run", "--no-capture-output", "-n", environment, *map(str, arguments)]
