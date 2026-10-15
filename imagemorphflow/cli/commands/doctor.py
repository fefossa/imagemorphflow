"""Read-only environment diagnostics for the portable core and external tools."""

import json
import os
import platform
import shutil
import sys
from importlib import metadata

import click

from imagemorphflow import __version__
from imagemorphflow.config import load_config


@click.command()
@click.option("--config", type=click.Path(exists=True, dir_okay=False), help="Also inspect resolved project settings.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable diagnostics.")
def doctor(config, as_json):
    """Show platform, core dependencies and external-tool availability."""
    try:
        settings = load_config(config) if config else {}
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    dependencies = {}
    for name in ("click", "PyYAML", "jsonschema", "numpy", "pandas", "Pillow", "pycytominer"):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = None
    candidate = settings.get("conda_executable") or os.environ.get("CONDA_EXE") or shutil.which("conda")
    conda = str(candidate) if candidate and (shutil.which(str(candidate)) or os.path.isfile(candidate)) else None
    report = {
        "imagemorphflow": __version__, "system": platform.system(), "architecture": platform.machine(),
        "python": platform.python_version(), "python_executable": sys.executable,
        "dependencies": dependencies, "conda_executable": conda,
        "image_link_mode": settings.get("image_link_mode", "auto"),
        "segmentation_device": settings.get("segmentation_device", "auto"),
        "scientific_tools_validated": False,
        "notes": [
            "Core image metadata, SQLite and CLI workflows are portable; scientific tool installations are separate.",
            "Auto image mode reads source images directly when directory symlinks are unavailable; it never copies the dataset.",
            "Conda detection does not establish that CellProfiler or micro-sam environments are installed.",
            "CUDA requires a supported NVIDIA device/runtime. Apple MPS depends on model support; CPU is an explicit fallback.",
        ],
    }
    if settings:
        report["project_root"] = settings["project_root"]
        report["workspace"] = settings["base_path"]
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo(f"ImageMorphFlow {__version__} — {report['system']} ({report['architecture']})")
        click.echo(f"Python: {report['python']} | Conda: {conda or 'not found (optional for the core)'}")
        click.echo(f"Images: {report['image_link_mode']} | Segmentation device: {report['segmentation_device']}")
        for note in report["notes"]:
            click.echo(f"- {note}")
