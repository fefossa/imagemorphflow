from support import temporary_directory
import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from imagemorphflow.config import load_config, load_mappings, validate_manifest
from imagemorphflow.processing.config_builder import ConfigBuilder, parse_overrides


def manifest(root="/tmp/imf-test"):
    return {"microscope": "imagexpress", "modality": "cellpainting", "mask_predict": False,
            "steps": ["analysis", "ingest", "join"], "overrides": {
                "project_name": "demo", "project_root": str(root), "image_path": "/tmp/images",
                "symlinks_file": "demo.json"}}


class ConfigTests(unittest.TestCase):
    def test_presets_and_resolution(self):
        for microscope, modality in (("imagexpress", "cellpainting"), ("endeavor", "cellpainting"), ("endeavor", "brightfield")):
            data = manifest()
            data.update(microscope=microscope, modality=modality)
            cfg = ConfigBuilder().build_config(data, "analysis")
            self.assertEqual(cfg["microscope"], microscope)
            self.assertEqual(Path(cfg["base_path"]), Path("/tmp/imf-test/workspace").resolve())
            self.assertEqual(Path(cfg["image_local_path"]), Path("/tmp/imf-test/images/images/{plate_new}").resolve())
            self.assertNotIn("{project_root}", json.dumps(cfg))

    def test_reject_invalid_manifest(self):
        for key, value in (("microscope", "unknown"), ("steps", ["bad"]), ("mask_predict", "false"), ("extra", 1)):
            data = manifest()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manifest(data)
        data = manifest()
        data["overrides"]["max_workers"] = 0
        with self.assertRaises(ValueError):
            validate_manifest(data)

    def test_invalid_combinations(self):
        data = manifest()
        data["overrides"]["normalize"] = {"perform": True}
        with self.assertRaisesRegex(ValueError, "annotate"):
            ConfigBuilder().build_config(data, "join")
        data = manifest()
        data["join_profile"] = "full"
        with self.assertRaisesRegex(ValueError, "platemap"):
            ConfigBuilder().build_config(data, "join")

    def test_overrides_do_not_mutate_inputs_and_support_dotted_keys(self):
        builder = ConfigBuilder()
        data = manifest()
        before = copy.deepcopy(data)
        cfg = builder.build_config(data, "join", parse_overrides(["feature_selection.perform=true", "max_workers=2"]))
        self.assertTrue(cfg["feature_selection"]["perform"])
        self.assertEqual(data, before)
        with self.assertRaises(ValueError):
            parse_overrides(["bad"])

    def test_effective_config_and_broken_latest_link(self):
        with temporary_directory() as directory:
            root = Path(directory)
            source = root / "manifest.json"
            source.write_text(json.dumps(manifest(root)))
            output = root / "configs"
            output.mkdir()
            try:
                (output / "latest_analysis.yaml").symlink_to("missing.yaml")
            except OSError:
                (output / "latest_analysis.yaml").write_text("stale config")
            builder = ConfigBuilder()
            cfg = builder.generate_effective_config(source, "analysis", output)
            self.assertEqual(load_config(output / "latest_analysis.yaml"), cfg)
            if (output / "latest_analysis.yaml").is_symlink():
                self.assertFalse(Path((output / "latest_analysis.yaml").readlink()).is_absolute())

    def test_legacy_workspace_override(self):
        data = manifest()
        del data["overrides"]["project_root"]
        data["overrides"]["base_path"] = "/tmp/custom/workspace"
        cfg = ConfigBuilder().build_config(data, "analysis")
        self.assertEqual(Path(cfg["project_root"]), Path("/tmp/custom").resolve())
        self.assertEqual(Path(cfg["image_local_path"]), Path("/tmp/custom/images/images/{plate_new}").resolve())

    def test_mappings_require_unique_nonempty_names(self):
        with temporary_directory() as directory:
            path = Path(directory) / "plates.json"
            for mappings in ({}, {"plate": ""}, {"p1": "x", "p2": "x"}, {"../p": "x"}):
                path.write_text(json.dumps(mappings))
                with self.assertRaises(ValueError):
                    load_mappings(path)
            path.write_text(json.dumps({"plate": "p01"}))
            self.assertEqual(load_mappings(path), {"plate": "p01"})

    def test_step_specific_pipeline_and_cli_precedence(self):
        data = manifest()
        data['steps'] = ['illum', 'analysis']
        data['step_overrides'] = {'illum': {'pipeline_file': 'custom-illum.cppipe'},
                                  'analysis': {'pipeline_file': 'custom-analysis.cppipe'}}
        builder = ConfigBuilder()
        self.assertEqual(builder.build_config(data, 'illum')['pipeline_file'], 'custom-illum.cppipe')
        self.assertEqual(builder.build_config(data, 'analysis')['pipeline_file'], 'custom-analysis.cppipe')
        self.assertEqual(builder.build_config(data, 'analysis', {'pipeline_file': 'cli.cppipe'})['pipeline_file'], 'cli.cppipe')
        self.assertFalse(builder.build_config(data, 'illum')['correct_illumination'])

    def test_mask_channels_are_validated(self):
        data = manifest()
        data['mask_predict'] = True
        with self.assertRaisesRegex(ValueError, 'unknown channels'):
            ConfigBuilder().build_config(data, 'analysis')
        data['overrides']['masks'] = {'mask_channels': {'MaskCells': 'OrigHoechst'}}
        data['overrides']['pattern_images'] = '*_w1_*.tif*'
        self.assertTrue(ConfigBuilder().build_config(data, 'analysis')['mask_predict'])
