"""Small execution records without environment variables or credentials."""

import hashlib
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from imagemorphflow import __version__
from imagemorphflow.portable import conda_command


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path):
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "exists": False}
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


def package_versions():
    versions = {"imagemorphflow": __version__}
    for name in ("numpy", "pandas", "scipy", "PyYAML", "pycytominer", "cellprofiler", "micro-sam", "cellpose"):
        try:
            dist = metadata.distribution(name)
            entry = {"version": dist.version}
            direct = dist.read_text("direct_url.json")
            if direct:
                # Record immutable revisions, never source URLs with possible credentials.
                vcs = json.loads(direct).get("vcs_info", {})
                if vcs.get("commit_id"):
                    entry["commit_id"] = vcs["commit_id"]
            versions[name] = entry
        except metadata.PackageNotFoundError:
            versions[name] = {"installed_in_current_python": False}
    return versions


class RunRecord:
    def __init__(self, script, config_path, config, command):
        directory = Path(config["base_path"]) / "logs" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{uuid.uuid4().hex}.json"
        self.data = {
            "script": script, "started_at": timestamp(), "status": "running",
            "python": platform.python_version(), "system": platform.system(), "os_release": platform.release(), "architecture": platform.machine(), "command": command,
            "config": fingerprint(config_path), "effective_config": config,
            "packages": package_versions(),
            "external_environments": {key: config[key] for key in ("cellprofiler_env", "sam_env") if key in config},
            "external_tool_versions": config.get("external_tool_versions", {}),
        }
        try:
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.data["source_commit"] = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        environment = config.get("cellprofiler_env") if script == "run_cellprofiler" else config.get("sam_env", "sam") if script.startswith("predict_masks") else None
        if environment:
            probe = "import json; from importlib.metadata import distributions; print(json.dumps({d.metadata['Name']: d.version for d in distributions() if d.metadata['Name'].lower() in ('cellprofiler', 'cellpose', 'micro-sam')}))"
            try:
                result = subprocess.run(conda_command(environment, ["python", "-c", probe], config.get("conda_executable")), capture_output=True, text=True, timeout=20)
                self.data["observed_external_versions"] = json.loads(result.stdout) if result.returncode == 0 else {"available": False}
            except (OSError, subprocess.TimeoutExpired, ValueError):
                self.data["observed_external_versions"] = {"available": False}
        if config.get("pipeline_file"):
            self.data["pipeline"] = fingerprint(Path(config["base_path"]) / "pipelines" / config["pipeline_file"])
        if config.get("model_path"):
            self.data["model"] = fingerprint(config["model_path"])
        if config.get("model"):
            self.data["model_type"] = config["model"]
        mapping = Path(config["base_path"]) / "symlinks" / config.get("symlinks_file", "plates.json")
        self.data["plate_mapping"] = fingerprint(mapping)
        self.save()

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n")
        temporary.replace(self.path)

    def finish(self, returncode, error=None):
        self.data.update(finished_at=timestamp(), returncode=returncode,
                         status="success" if returncode == 0 else "failed")
        if error:
            self.data["error"] = str(error)
        self.save()
