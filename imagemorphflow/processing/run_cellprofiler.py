"""Run CellProfiler and preserve its failure status."""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from imagemorphflow.config import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    log_dir = Path(config["base_path"]) / "logs" / "run_cellprofiler"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f") + "_run.log")
    command = [sys.executable, "-m", "imagemorphflow.utils.run_cellprofiler_utils", "--config", args.config]
    print(f"CellProfiler log: {log_path}", flush=True)
    with log_path.open("w") as log_file:
        result = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT)
    if result.returncode:
        print(f"[ERROR] CellProfiler failed. See {log_path}", file=sys.stderr)
        raise SystemExit(result.returncode if result.returncode > 0 else 1)
    print(f"[OK] CellProfiler completed. Log: {log_path}")


if __name__ == "__main__":
    main()
