import os
import subprocess
import logging
import yaml
import glob
import csv
import fnmatch
from pathlib import Path
from imagemorphflow.portable import conda_command
from datetime import datetime


def setup_logging(project_name, base_path):
    log_dir = os.path.join(base_path, "logs", "predict_masks")
    os.makedirs(log_dir, exist_ok=True)
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    error_log_path = os.path.join(log_dir, f"{current_time}_error_log.log")

    logging.basicConfig(
        filename=error_log_path,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    return logging.getLogger("error_logger")


def run_segmentation(cmd):
    """Run the micro_sam automatic segmentation command."""
    full_cmd = cmd
    logging.info(f"STARTING: {' '.join(full_cmd)}")
    try:
        result = subprocess.run(
            full_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,  # decode bytes to string
        )
        logging.info(f"FINISHED: {' '.join(full_cmd)}")
        logging.debug(f"STDOUT: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"FAILED: {' '.join(full_cmd)}")
        logging.error(f"STDOUT: {e.stdout}")
        logging.error(f"STDERR: {e.stderr}")
        return False


def get_images(image_path, pattern, data_file=None):
    # Use glob to match files with the given pattern
    if data_file and Path(data_file).is_file():
        image_files = []
        with open(data_file, newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                for key, name in row.items():
                    if key.startswith("FileName_") and not key.startswith("FileName_Illum") and fnmatch.fnmatch(name, pattern):
                        path_key = key.replace("FileName_", "PathName_", 1)
                        image_files.append(os.path.join(row[path_key], name))
        image_files = sorted(set(image_files))
    else:
        image_files = sorted(glob.glob(os.path.join(image_path, pattern)))

    # Get the file names (i.e., just the base names without directories)
    file_names = [os.path.basename(file) for file in image_files]

    return image_files, file_names


def generate_segmentation_command(image_path, output_dir, plate, config):
    """
    Generate the segmentation command for each plate based on config.
    The command runs micro_sam.automatic_segmentation for each image.
    """

    model = config["model"]
    pattern_images = config["pattern_images"]
    os.makedirs(output_dir, exist_ok=True)
    data_file = Path(config["base_path"]) / "loaddata" / plate / "load_data.csv"
    image_files, file_names = get_images(image_path, pattern_images, data_file)
    output_files = [os.path.join(output_dir, file_name) for file_name in file_names]

    commands = []
    for img in range(len(image_files)):
        cmd = [
            "micro_sam.automatic_segmentation",
            "--input_path",
            image_files[img],
            "--output_path",
            output_files[img],
            # "-e",
            # output_dir, # do not include those flags when calling command for each image separately
            # "--pattern",
            # pattern_images,
            "--model_type",
            model,
            "--tile_shape",
            *[str(value) for value in config.get("tile_shape", [512, 512])],
            "--halo",
            *[str(value) for value in config.get("halo", [128, 128])],
            "--batch_size",
            "4",
            "--verbose",
            # "--device",
            # "cpu",
        ]
        device = config.get("segmentation_device", "auto")
        if device != "auto":
            cmd.extend(["--device", device])
        commands.append(conda_command(config.get("sam_env", "sam"), cmd, config.get("conda_executable")))

    return commands


def dry_run():
    return [["micro_sam.automatic_segmentation -h"]]
