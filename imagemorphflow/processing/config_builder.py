"""Build validated, effective configurations from presets and manifests."""

import argparse
import copy
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import yaml

from imagemorphflow.config import STEPS, resolve_config, validate_config, validate_manifest
from imagemorphflow.portable import latest_config

DEFAULT_CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


class ConfigBuilder:
    def __init__(self, configs_dir=DEFAULT_CONFIGS_DIR, base_config="base.yaml"):
        self.configs_dir = Path(configs_dir)
        self.base_config_path = self.configs_dir / base_config
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    def load_yaml(self, filepath):
        with open(filepath, encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError(f"Configuration must be an object: {filepath}")
        return data

    def save_yaml(self, data, filepath):
        with open(filepath, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=True)

    def load_manifest(self, manifest_path):
        with open(manifest_path, encoding="utf-8") as stream:
            return validate_manifest(json.load(stream))

    def deep_merge(self, base, override):
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def build_config(self, manifest, step, cli_overrides=None):
        validate_manifest(manifest)
        if step not in STEPS:
            raise ValueError(f"Unknown processing step: {step}")
        modality, microscope = manifest["modality"], manifest["microscope"]
        config = self.load_yaml(self.base_config_path)
        modality_file = "brightfield.yaml" if modality == "brightfield" else f"cellpainting.{microscope}.yaml"
        overlays = [self.configs_dir / "modality" / modality_file,
                    self.configs_dir / "mask" / ("on.yaml" if manifest.get("mask_predict", False) else "off.yaml")]
        if step == "illum":
            filename = f"cellpainting.{microscope}.yaml" if modality == "cellpainting" else "illum.dummy.yaml"
            overlays.append(self.configs_dir / "illum" / filename)
            if modality != "cellpainting":
                warnings.warn("Verify whether illumination correction is needed for brightfield", UserWarning)
        elif step == "analysis":
            overlays.append(self.configs_dir / f"analysis.{microscope}.yaml")
        elif step == "join":
            overlays.append(self.configs_dir / f"join.{manifest.get('join_profile', 'basic')}.yaml")
        for overlay in overlays:
            # Missing presets are errors, not silently ignored configuration.
            config = self.deep_merge(config, self.load_yaml(overlay))
        config["correct_illumination"] = step != "illum" and "illum" in manifest["steps"]
        overrides = self.deep_merge(manifest.get("overrides", {}), manifest.get("step_overrides", {}).get(step, {}))
        overrides = self.deep_merge(overrides, cli_overrides or {})
        if "base_path" in overrides and "project_root" not in overrides:
            config.pop("project_root", None)
        config = self.deep_merge(config, overrides)
        if "channels" in overrides:
            config["channels"] = copy.deepcopy(overrides["channels"])
        config["microscope"] = microscope
        config["modality"] = modality
        config["mask_predict"] = manifest.get("mask_predict", False)
        # Step type cannot be overridden globally (e.g. analysis accidentally used for illum).
        if step in ("illum", "analysis"):
            config["pipeline_type"] = step
        if step == "illum":
            config["correct_illumination"] = False
        validate_config(config)
        return validate_config(resolve_config(config))

    def generate_effective_config(self, manifest_path, step, output_dir=None, cli_overrides=None):
        manifest = self.load_manifest(manifest_path)
        config = self.build_config(manifest, step, cli_overrides)
        effective_dir = Path(output_dir).resolve() if output_dir else Path(config["base_path"]) / "configs" / "effective"
        effective_dir.mkdir(parents=True, exist_ok=True)
        config_filename = effective_dir / f"{self.timestamp}_{step}.yaml"
        self.save_yaml(config, config_filename)
        latest_link = effective_dir / f"latest_{step}.yaml"
        latest_config(config_filename, latest_link)
        (effective_dir / f"{self.timestamp}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"[INFO] Effective config -> {config_filename}")
        return config


def parse_overrides(values):
    overrides = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError(f"Override must use key=value: {item}")
        key, value = item.split("=", 1)
        target = overrides
        parts = key.split(".")
        if not all(parts):
            raise ValueError(f"Invalid override key: {key}")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = yaml.safe_load(value)
    return overrides


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--manifest", required=True)
    parser.add_argument("-s", "--step", choices=STEPS)
    parser.add_argument("-c", "--configs-dir", default=str(DEFAULT_CONFIGS_DIR))
    parser.add_argument("-o", "--output-dir")
    parser.add_argument("-O", "--override", action="append")
    args = parser.parse_args()
    try:
        builder = ConfigBuilder(args.configs_dir)
        manifest = builder.load_manifest(args.manifest)
        overrides = parse_overrides(args.override)
        steps = [args.step] if args.step else manifest["steps"]
        for step in steps:
            builder.generate_effective_config(args.manifest, step, args.output_dir, overrides)
    except (ValueError, OSError, yaml.YAMLError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
