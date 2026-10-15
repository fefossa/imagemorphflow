"""Install a built wheel outside the source tree and exercise CLI/resources."""

import os
import glob
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    candidates = glob.glob(sys.argv[1])
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one wheel, got {candidates}")
    wheel = Path(candidates[0]).resolve()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # Dependencies are supplied by the CI job; only the package comes from the wheel.
        venv.create(root / "env", with_pip=True, system_site_packages=True)
        python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        env["PYTHONNOUSERSITE"] = "1"
        def run(args):
            subprocess.run([str(python), *args], cwd=root, env=env, check=True)
        run(["-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)])
        run(["-m", "imagemorphflow.cli", "--help"])
        run(["-m", "imagemorphflow.cli", "--version"])
        probe = '''from pathlib import Path
import imagemorphflow
from imagemorphflow.processing.config_builder import ConfigBuilder
from imagemorphflow.config import validate_manifest
root = Path(imagemorphflow.__file__).resolve()
assert "env" in root.parts, root
manifest = {"microscope":"imagexpress", "modality":"cellpainting", "steps":["analysis"], "overrides":{"project_name":"smoke", "image_path":"/tmp/images", "symlinks_file":"plates.json"}}
validate_manifest(manifest)
assert ConfigBuilder().build_config(manifest, "analysis")["pipeline_type"] == "analysis"
from imagemorphflow.utils import ingest_profiles_utils
print("Wheel imports, CLI, schema and packaged YAML presets verified")
'''
        run(["-c", probe])


if __name__ == "__main__":
    main()
