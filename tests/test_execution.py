from support import temporary_directory
import json
import logging
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from imagemorphflow import __version__
from imagemorphflow.cli.cli import cli
from imagemorphflow.cli.commands.run_pipeline import plan_steps
from imagemorphflow.processing import run_cellprofiler
from imagemorphflow.utils import run_cellprofiler_utils as cp
from test_config import manifest


class InlineExecutor:
    """Run real batch coordination with a deterministic executor."""
    def __init__(self, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as error:
            future.set_exception(error)
        return future


class ExecutionTests(unittest.TestCase):
    def test_cli_version_and_required_arguments(self):
        runner = CliRunner()
        self.assertIn(__version__, runner.invoke(cli, ["--version"]).output)
        self.assertNotEqual(runner.invoke(cli, ["run"]).exit_code, 0)
        self.assertNotEqual(runner.invoke(cli, ["build"]).exit_code, 0)

    def test_plan_orders_prerequisites_and_optional_masks(self):
        data = manifest()
        self.assertEqual(plan_steps(data), ["init", "load_data", "analysis", "ingest", "join"])
        data["mask_predict"] = True
        data["overrides"]["use_scratch"] = True
        self.assertEqual(plan_steps(data), ["init", "copy_to_scratch", "load_data", "predict_masks", "analysis", "ingest", "join"])

    def test_dry_run_has_no_side_effects(self):
        with temporary_directory() as directory:
            root = Path(directory)
            source = root / "manifest.json"
            source.write_text(json.dumps(manifest(root / "project")))
            with patch("imagemorphflow.cli.commands.run_pipeline.subprocess.run") as run:
                result = CliRunner().invoke(cli, ["run", "--manifest", str(source), "--dry-run"])
            self.assertEqual(result.exit_code, 0, result.output)
            run.assert_not_called()
            self.assertFalse((root / "project").exists())

    def test_failure_stops_pipeline_and_records_error(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / "symlinks").mkdir()
            (root / "symlinks" / "plates.json").write_text('{"raw":"p01"}')
            source = root / "manifest.json"
            data = manifest(root.parent / "unused")
            data["steps"] = ["ingest", "join"]
            data["overrides"].update(base_path=str(root), symlinks_file="plates.json")
            source.write_text(json.dumps(data))
            real_run = subprocess.run
            def command(cmd, **kwargs):
                if isinstance(cmd, list) and cmd[0] == "git":
                    return subprocess.CompletedProcess(cmd, 1, stdout="")
                if isinstance(cmd, list) and cmd[0] == sys.executable:
                    return subprocess.CompletedProcess(cmd, 7)
                # Python 3.9 on Windows may probe the OS with the `ver` command.
                # Only the processing child is simulated as failed.
                return real_run(cmd, **kwargs)
            with patch("imagemorphflow.cli.commands.run_pipeline.subprocess.run", side_effect=command):
                result = CliRunner().invoke(cli, ["run", "--manifest", str(source)])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("return code 7", result.output, repr(result.exception))
            records = list((root / "logs" / "runs").glob("*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["returncode"], 7)
            self.assertIn("sha256", record["config"])

    def test_cellprofiler_retry_exhaustion_is_error(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / "pipelines").mkdir()
            (root / "pipelines" / "analysis.cppipe").touch()
            (root / "loaddata" / "p01").mkdir(parents=True)
            (root / "loaddata" / "p01" / "load_data.csv").write_text("header\nrow\n")
            cfg = {"illum_out_path": str(root), "correct_illumination": False, "pipeline_file": "analysis.cppipe",
                   "plugins_dir": str(root), "pipeline_type": "analysis", "cellprofiler_env": "cp", "max_workers": 1}
            with patch.object(cp, "ProcessPoolExecutor", InlineExecutor), patch.object(cp, "run_cellprofiler", return_value=False) as run:
                with self.assertRaisesRegex(RuntimeError, "batches failed"):
                    cp.run_batches(cfg, "p01", root, logging.getLogger("test"), "user")
            self.assertEqual(run.call_count, 2)

    def test_cellprofiler_retry_recovery_succeeds(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / "pipelines").mkdir()
            (root / "pipelines" / "a.cppipe").touch()
            (root / "loaddata" / "p01").mkdir(parents=True)
            (root / "loaddata" / "p01" / "load_data.csv").write_text("h\nr\n")
            cfg = {"illum_out_path": str(root), "correct_illumination": False, "pipeline_file": "a.cppipe",
                   "plugins_dir": str(root), "pipeline_type": "analysis", "cellprofiler_env": "cp"}
            with patch.object(cp, "ProcessPoolExecutor", InlineExecutor), patch.object(cp, "run_cellprofiler", side_effect=[False, True]):
                cp.run_batches(cfg, "p01", root, logging.getLogger("test"), "user")

    def test_cellprofiler_wrapper_preserves_exit_code(self):
        with temporary_directory() as directory:
            root = Path(directory)
            config = root / "config.yaml"
            config.write_text(yaml.safe_dump({"base_path": str(root), "project_name": "demo"}))
            with patch.object(sys, "argv", ["run_cellprofiler", "--config", str(config)]), \
                 patch.object(run_cellprofiler.subprocess, "run", return_value=subprocess.CompletedProcess([], 9)):
                with self.assertRaises(SystemExit) as error:
                    run_cellprofiler.main()
            self.assertEqual(error.exception.code, 9)

    def test_illumination_plate_failure_reaches_coordinator(self):
        with temporary_directory() as directory:
            root = Path(directory)
            (root / 'symlinks').mkdir()
            (root / 'symlinks' / 'plates.json').write_text('{"raw":"p01"}')
            cfg = {'base_path': str(root), 'project_name': 'demo', 'symlinks_file': 'plates.json', 'pipeline_type': 'illum'}
            path = root / 'config.yaml'
            path.write_text(yaml.safe_dump(cfg))
            with patch.object(cp, 'ProcessPoolExecutor', InlineExecutor), patch.object(cp, 'run_batches', side_effect=RuntimeError('failed batch')):
                with self.assertRaisesRegex(RuntimeError, 'failed for plates'):
                    cp.process_all(path)

    def test_mask_retry_exhaustion_is_error(self):
        from imagemorphflow.processing import predict_masks
        with temporary_directory() as directory:
            root = Path(directory)
            (root / 'symlinks').mkdir()
            (root / 'symlinks' / 'plates.json').write_text('{"raw":"p01"}')
            path = root / 'config.json'
            path.write_text(json.dumps({'base_path': str(root), 'project_name': 'demo', 'symlinks_file': 'plates.json',
                                        'image_local_path': str(root / '{plate_new}'), 'masks': {'mask_output_dir': str(root / 'masks' / '{plate_new}')}}))
            with patch.object(predict_masks, 'ThreadPoolExecutor', InlineExecutor), \
                 patch.object(predict_masks.predict_masks_utils, 'generate_segmentation_command', return_value=[['micro_sam.automatic_segmentation']]), \
                 patch.object(predict_masks.predict_masks_utils, 'run_segmentation', return_value=False) as run:
                with self.assertRaisesRegex(RuntimeError, 'segmentation commands failed'):
                    predict_masks.process_segmentations(path)
            self.assertEqual(run.call_count, 2)
