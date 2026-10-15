"""Configuration validation and shared path resolution."""

import copy
import getpass
import json
import os
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

STEPS = ("init", "copy_to_scratch", "load_data", "predict_masks", "illum", "analysis", "ingest", "join")


def username():
    return os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()


def validate_manifest(manifest):
    schema = json.loads((Path(__file__).parent / "schemas" / "manifest.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        location = ".".join(str(p) for p in error.absolute_path) or "manifest"
        raise ValueError(f"{location}: {error.message}")
    if manifest["modality"] == "brightfield" and manifest["microscope"] != "endeavor":
        raise ValueError("brightfield currently supports only the endeavor microscope")
    if "predict_masks" in manifest["steps"] and not manifest.get("mask_predict", False):
        raise ValueError("predict_masks requires mask_predict=true")
    return manifest


def resolve_config(config):
    """Resolve shared paths once, retaining per-plate placeholders for callers."""
    result = copy.deepcopy(config)
    project_name = result.get("project_name", "my_project")
    root = result.get("project_root")
    if root is None:
        root = str(Path(result["base_path"]).parent) if "base_path" in result else "~/projects/{project_name}"
    substitutions = {"username": username(), "project_name": project_name}

    def expand(text):
        for key, value in substitutions.items():
            text = text.replace("{" + key + "}", str(value))
        return os.path.expanduser(os.path.expandvars(text))

    substitutions["project_root"] = str(Path(expand(root)).resolve())
    substitutions["base_path"] = str(Path(expand(result.get("base_path", "{project_root}/workspace"))).resolve())

    def visit(value):
        if isinstance(value, dict):
            return {k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        return expand(value) if isinstance(value, str) else value

    result = visit(result)
    result["project_root"] = substitutions["project_root"]
    result["base_path"] = substitutions["base_path"]
    return result


def validate_config(config):
    """Reject incompatible switches and invalid resource limits early."""
    if config.get("image_link_mode", "auto") not in ("auto", "symlink", "reference"):
        raise ValueError("image_link_mode must be auto, symlink or reference")
    if config.get("segmentation_device", "auto") not in ("auto", "cpu", "cuda", "mps"):
        raise ValueError("segmentation_device must be auto, cpu, cuda or mps")
    for field in ("images_per_process", "max_parallel_plates", "max_workers", "mask_workers"):
        value = config.get(field, 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
    for section in ("annotate", "normalize", "feature_selection"):
        value = config.get(section, {})
        if not isinstance(value, dict) or not isinstance(value.get("perform", False), bool):
            raise ValueError(f"{section}.perform must be a boolean")
    if config.get("normalize", {}).get("perform") and not config.get("annotate", {}).get("perform"):
        raise ValueError("normalize.perform requires annotate.perform=true")
    if config.get("annotate", {}).get("perform") and not config["annotate"].get("platemap"):
        raise ValueError("annotate.platemap is required when annotation is enabled")
    masks = config.get("masks", {})
    if masks.get("include_masks"):
        channels = set(config.get("channels", {}).values())
        missing = set(masks.get("mask_channels", {}).values()) - channels
        if missing:
            raise ValueError(f"masks.mask_channels reference unknown channels: {sorted(missing)}")
        if not masks.get("mask_output_dir") or not masks.get("mask_channels"):
            raise ValueError("Masks require mask_output_dir and mask_channels")
    if config.get("mask_predict") and masks.get("segmentation_method") != "microsam":
        raise ValueError("Standalone mask prediction uses microsam; Cellpose runs inside a CellProfiler pipeline")
    for field in ("image_path", "base_path", "project_root"):
        if field in config and (not isinstance(config[field], str) or not config[field].strip()):
            raise ValueError(f"{field} must be a non-empty path")
    return config


def load_config(path):
    with open(path, encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Config must be a YAML or JSON object")
    validate_config(config)
    return validate_config(resolve_config(config))


def portable_folder_name(name):
    if not isinstance(name, str) or not name.strip() or name in (".", "..") or name.endswith((".", " ")):
        return False
    if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
        return False
    return not re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", name.split(".")[0], flags=re.IGNORECASE)


def load_mappings(path):
    with open(path, encoding="utf-8") as stream:
        mappings = json.load(stream)
    if not isinstance(mappings, dict) or not mappings:
        raise ValueError(f"No plate mappings in {path}")
    for source, target in mappings.items():
        if not all(portable_folder_name(name) for name in (source, target)):
            raise ValueError(f"Complete plate mappings in {path}; names must be portable, non-empty folder names")
    if len({name.casefold() for name in mappings.values()}) != len(mappings):
        raise ValueError(f"Plate names must be unique ignoring case in {path}")
    return mappings
