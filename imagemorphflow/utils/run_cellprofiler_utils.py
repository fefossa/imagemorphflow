from imagemorphflow.config import load_config
from imagemorphflow.portable import conda_command
import os
import subprocess
import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from imagemorphflow.utils import file_utils
from typing import Optional


def setup_logging_cellprofiler(base_path: str, plate: Optional[str] = None):
    """
    Create a logfile under <base_path>/logs/run_cellprofiler/.
    If 'plate' is provided, include it in the filename to keep logs separate per plate.
    """
    log_dir = os.path.join(base_path, "logs", "run_cellprofiler")
    os.makedirs(log_dir, exist_ok=True)
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{plate}" if plate else ""
    error_log_path = os.path.join(log_dir, f"{current_time}{suffix}_error_log.log")

    logging.basicConfig(
        filename=error_log_path,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    return logging.getLogger("error_logger")


def count_data_rows(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        next(f)
        return sum(1 for _ in f)


def run_cellprofiler(cmd, cellprofiler_env, conda_executable=None):
    full_cmd = conda_command(cellprofiler_env, cmd, conda_executable)
    logging.info(f"STARTING: {' '.join(full_cmd)}")
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    env.setdefault("MKL_NUM_THREADS", "2")

    try:
        # subprocess.run(cmd, check=True)
        full_cmd = conda_command(cellprofiler_env, cmd, conda_executable)
        subprocess.run(full_cmd, check=True, env=env)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed: {' '.join(cmd)} — {e}")
        return False


def run_batches(config, plate, base_path: Path, logger, username):
    """
    Run CellProfiler for a given plate.
    - For 'illum' we run one command per plate (illum needs all images), and parallelize across plates in process_all().
    - For other pipeline types, we split images into chunks and run them in parallel within this plate.
    """
    # If called from a child process with logger=None, create a per-plate logger here
    if logger is None:
        logger = setup_logging_cellprofiler(str(base_path), plate=plate)

    num_cores = min(file_utils.get_num_cores(0.7), int(config.get("max_workers", 4)))
    illum_path_template = config["illum_out_path"]
    if config.get("correct_illumination", True):
        load_data_file = "load_data_with_illum.csv"
    else:
        load_data_file = "load_data.csv"

    pipeline_file = os.path.join(base_path, "pipelines", config["pipeline_file"])
    temp_dir = os.path.join(base_path, "temp", "cellprofiler")
    os.makedirs(temp_dir, exist_ok=True)
    plugin_dir = config["plugins_dir"].format(username=username)

    pipeline_type = config["pipeline_type"]
    cellprofiler_env = config["cellprofiler_env"]

    if pipeline_type == "assaydev":
        output_dir = os.path.join(base_path, "assaydev", plate)
    elif pipeline_type == "illum":
        output_dir = illum_path_template.format(
            username=username,
            project_name=config["project_name"],
            plate_new=plate,
        )
    elif pipeline_type == "analysis":
        output_dir = os.path.join(base_path, "backend", plate)
    else:
        logger.error("Invalid pipeline type specified in config.")
        sys.exit(1)

    data_file = os.path.join(base_path, "loaddata", plate, load_data_file)
    if not Path(pipeline_file).is_file():
        raise FileNotFoundError(f"CellProfiler pipeline missing: {pipeline_file}")
    total_images = count_data_rows(data_file)
    if total_images == 0:
        raise ValueError(f"No images in {data_file}")
    images = list(range(1, total_images + 1))

    os.makedirs(output_dir, exist_ok=True)

    if pipeline_type == "illum":
        commands = [
            [
                "cellprofiler",
                "-c",
                "-r",
                "-p",
                pipeline_file,
                "-o",
                output_dir,
                "--data-file",
                data_file,
                "-t",
                temp_dir,
                "--plugins-directory",
                plugin_dir,
                "--log-level",
                "INFO",
                "--conserve-memory=CONSERVE_MEMORY",
            ]
        ]

    else:
        images_per_process = int(config.get("images_per_process", 6))
        if images_per_process < 1:
            raise ValueError("images_per_process must be positive")
        commands = []
        for i in range(0, len(images), images_per_process):
            start = images[i]
            end = images[min(i + images_per_process - 1, len(images) - 1)]
            commands.append(
                [
                    "cellprofiler",
                    "-c",
                    "-r",
                    "-p",
                    pipeline_file,
                    "-o",
                    output_dir,
                    "--data-file",
                    data_file,
                    "-f",
                    str(start),
                    "-l",
                    str(end),
                    "-t",
                    temp_dir,
                    "--plugins-directory",
                    plugin_dir,
                    "--log-level",
                    "INFO",
                    "--conserve-memory=CONSERVE_MEMORY",
                ]
            )

    failed = []
    # Note: for illum there is only one command; inner parallelism is mainly for non-illum
    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        futures = {
            executor.submit(run_cellprofiler, cmd, cellprofiler_env, config.get("conda_executable")): cmd
            for cmd in commands
        }
        for future in as_completed(futures):
            ok = future.result()
            if not ok:
                failed_cmd = futures[future]
                failed.append(failed_cmd)
                logger.error(f"Failed: {' '.join(failed_cmd)}")

    if failed:
        logger.warning(f"Attempting to retry {len(failed)} failed commands.")
        persistent_failures = []
        for cmd in failed:
            logger.info(f"Retrying failed command: {' '.join(cmd)}")
            if not run_cellprofiler(cmd, cellprofiler_env, config.get("conda_executable")):
                persistent_failures.append(cmd)
                logger.critical(f"Retry failed for command: {' '.join(cmd)}")
        if persistent_failures:
            raise RuntimeError(f"{len(persistent_failures)} CellProfiler batches failed for plate {plate}")
    else:
        logger.info("All CellProfiler batches completed successfully.")


def process_all(config_path):
    config = load_config(config_path)
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    logger = setup_logging_cellprofiler(
        config["base_path"].format(
            username=username, project_name=config["project_name"]
        )
    )

    base_path = Path(
        config["base_path"].format(
            username=username, project_name=config["project_name"]
        )
    )

    # Top-level logger (used for coordinator logs)
    top_logger = setup_logging_cellprofiler(str(base_path))

    json_file = base_path / "symlinks" / config["symlinks_file"]
    symlink_mappings = file_utils.load_symlink_mappings(json_file)
    plates = list(symlink_mappings.values())

    pipeline_type = config["pipeline_type"]

    if pipeline_type == "illum":
        # Parallelize ACROSS plates
        max_parallel_plates = int(config.get("max_parallel_plates", 3))
        top_logger.info(
            f"Running illum across {len(plates)} plates "
            f"(max_parallel_plates={max_parallel_plates})."
        )
        plate_failures = []
        with ProcessPoolExecutor(max_workers=max_parallel_plates) as executor:
            futures = {
                executor.submit(
                    run_batches, config, plate, base_path, None, username
                ): plate
                for plate in plates
            }
            for future in as_completed(futures):
                plate = futures[future]
                try:
                    future.result()
                    top_logger.info(f"Finished plate: {plate}")
                except Exception as e:
                    top_logger.exception(f"Plate {plate} crashed: {e}")
                    plate_failures.append(plate)
        if plate_failures:
            raise RuntimeError(f"CellProfiler failed for plates: {plate_failures}")
    else:
        # Sequential over plates; each plate parallelizes internally over image chunks
        for plate in plates:
            top_logger.info(f"Processing plate: {plate}")
            run_batches(config, plate, base_path, top_logger, username)
            top_logger.info(f"Finished plate: {plate}")
    
    # Remove temporary CellProfiler measurement files created via -t
    temp_dir = Path(base_path, "temp", "cellprofiler")
    for h5_file in temp_dir.glob("Cpmeasurements*.hdf5"):
        h5_file.unlink()
        top_logger.info(f"Removed temporary file: {h5_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CellProfiler pipeline")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    print(f"Running run_cellprofiler.py with config: {args.config}")
    process_all(args.config)
