"""Validated CLI entry points and manifest-driven execution."""

import shlex
import os
import subprocess
import sys
from pathlib import Path

import click
import yaml

from imagemorphflow import __version__
from imagemorphflow.config import STEPS, load_config, load_mappings
from imagemorphflow.processing.config_builder import ConfigBuilder, parse_overrides
from imagemorphflow.provenance import RunRecord

SCRIPTS = {
    "init": "initialize_project_structure", "copy_to_scratch": "copy_to_scratch",
    "load_data": "load_data", "predict_masks": "predict_masks",
    "illum": "run_cellprofiler", "analysis": "run_cellprofiler",
    "ingest": "ingest_profiles", "join": "join_profiles",
}
AVAILABLE_SCRIPTS = tuple(sorted(set(SCRIPTS.values()) | {"plate_overview", "predict_masks_sam"}))


def plan_steps(manifest):
    """Order explicitly requested stages and add image-setup prerequisites."""
    steps = set(manifest["steps"])
    if steps.intersection({"analysis", "illum", "predict_masks", "load_data"}):
        steps.update({"init", "load_data"})
        if manifest.get("overrides", {}).get("use_scratch"):
            steps.add("copy_to_scratch")
        if manifest.get("mask_predict"):
            steps.add("predict_masks")
    if "analysis" in steps and "join" in steps:
        steps.add("ingest")
    return [step for step in STEPS if step in steps]


def run_script(script, config_path):
    config = load_config(config_path)
    if script != "initialize_project_structure":
        load_mappings(Path(config["base_path"]) / "symlinks" / config["symlinks_file"])
    command = [sys.executable, "-m", f"imagemorphflow.processing.{script}", "--config", str(config_path)]
    record = RunRecord(script, config_path, config, command)
    click.echo(f"Executing: {shlex.join(command)}")
    try:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        result = subprocess.run(command, env=environment)  # Stream long scientific runs.
    except BaseException as error:
        record.finish(1, error)
        raise
    record.finish(result.returncode)
    if result.returncode:
        raise click.ClickException(f"Script '{script}' failed with return code {result.returncode}; record: {record.path}")


@click.command("run")
@click.version_option(__version__, prog_name="imagemorphflow")
@click.option("-s", "--script", type=click.Choice(AVAILABLE_SCRIPTS))
@click.option("-c", "--config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-m", "--manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Validate and display the plan without writing or executing.")
def run_pipeline(script, config, manifest, dry_run):
    """Run SCRIPT with CONFIG, or execute the stages selected by MANIFEST."""
    if bool(manifest) == bool(config) or (manifest and script) or (config and not script):
        raise click.UsageError("Use --manifest FILE, or --script NAME --config FILE")
    try:
        if manifest:
            builder = ConfigBuilder()
            data = builder.load_manifest(manifest)
            steps = plan_steps(data)
            # Validate every stage before starting any work.
            for step in steps:
                builder.build_config(data, step)
            for step in steps:
                click.echo(f"{step}: {SCRIPTS[step]}")
                if not dry_run:
                    effective = builder.generate_effective_config(manifest, step)
                    path = Path(effective["base_path"]) / "configs" / "effective" / f"{builder.timestamp}_{step}.yaml"
                    run_script(SCRIPTS[step], path)
        else:
            load_config(config)
            if dry_run:
                click.echo(f"{script}: {config}")
            else:
                run_script(script, config)
    except (ValueError, OSError, yaml.YAMLError) as error:
        raise click.ClickException(str(error)) from error


@click.command("build")
@click.option("-m", "--manifest", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-s", "--step", type=click.Choice(STEPS))
@click.option("-o", "--output-dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("-O", "--override", multiple=True, help="Override a setting; dotted keys are supported.")
def build_config(manifest, step, output_dir, override):
    """Build effective configs for the requested manifest stages."""
    try:
        builder = ConfigBuilder()
        data = builder.load_manifest(manifest)
        overrides = parse_overrides(override)
        steps = [step] if step else data["steps"]
        for selected in steps:
            builder.build_config(data, selected, overrides)
        for selected in steps:
            builder.generate_effective_config(manifest, selected, output_dir, overrides)
    except (ValueError, OSError, yaml.YAMLError) as error:
        raise click.ClickException(str(error)) from error
