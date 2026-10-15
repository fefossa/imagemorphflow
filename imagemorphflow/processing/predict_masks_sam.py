from imagemorphflow.portable import plate_image_directory
from imagemorphflow.config import load_config, load_mappings as load_symlink_mappings
# Script to run micro-sam for one image after the other for GPU
# 15 seconds per image
# To run
# conda activate sam
# python predict_masks_sam --config 

import os
import yaml
import json
import glob
import logging
import subprocess
from datetime import datetime
from pathlib import Path


def get_num_cores(fraction=0.8):
    total_cores = os.cpu_count() or 1
    return max(1, int(total_cores * fraction))


def process_segmentations(config_path):
    config = load_config(config_path)
    image_path_template = config["image_local_path"]
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    output_dir_template = config["base_path"]

    masks_config = config.get("masks", {})
    mask_output_dir_template = masks_config.get("mask_output_dir", None)

    logger = setup_logging(
        config["project_name"],
        config["base_path"].format(
            username=username, project_name=config["project_name"]
        ),
    )

    output_dir = Path(
        output_dir_template.format(
            username=username, project_name=config["project_name"]
        )
    )
    json_file = output_dir / "symlinks" / config["symlinks_file"]
    symlink_mappings = load_symlink_mappings(json_file)

    failed = []
    for plate_old, plate_new in symlink_mappings.items():
        # Input path uses plate_new (symlinks)
        image_path = str(plate_image_directory(config, plate_new))
        
        # Output path uses plate_old (real names)
        mask_output_dir = mask_output_dir_template.format(
            username=username,
            project_name=config["project_name"],
            plate_new=plate_old,  # Use plate_old for output directory
        )
        
        # Create output directory before running SAM
        os.makedirs(mask_output_dir, exist_ok=True)
        
        commands = generate_segmentation_command(
            image_path, mask_output_dir, plate_old, plate_new, config
        )
        logger.info(f"Starting plate: {plate_new} -> {plate_old}")
        
        for cmd in commands:
            success = run_segmentation(cmd)
            if not success:
                failed.append(cmd)
                logger.error(f"Failed: {' '.join(cmd)}")
        
        # Create symlinks after successful processing
        if success:
            create_symlinks_for_masks(mask_output_dir, image_path, plate_new, config, logger)

    # Retry failed commands
    persistent_failures = []
    for cmd in failed:
        logger.info(f"Retrying failed command: {' '.join(cmd)}")
        if not run_segmentation(cmd):
            persistent_failures.append(cmd)
    if persistent_failures:
        raise RuntimeError(f"{len(persistent_failures)} segmentation commands failed")


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


def get_images(image_path, pattern):
    image_files = glob.glob(os.path.join(image_path, pattern))
    file_names = [os.path.basename(file) for file in image_files]
    return image_files, file_names


def generate_segmentation_command(image_path, output_dir, plate_old, plate_new, config):
    """
    Generate the segmentation command for each plate based on config.
    The command runs micro_sam.automatic_segmentation for the entire directory.
    """
    model = config["model"]
    pattern_images = config["pattern_images"]
    tile_shape = config.get("tile_shape", [512, 512])
    halo = config.get("halo", [64, 64])
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Single command to process all images in the directory
    cmd = [
        "micro_sam.automatic_segmentation",
        "--input_path", image_path,  # Uses plate_new (symlinks)
        "--output_path", output_dir,  # Uses plate_old (real directory)
        "--pattern", pattern_images,
        "--model_type", model,
        "--tile_shape", str(tile_shape[0]), str(tile_shape[1]),
        "--halo", str(halo[0]), str(halo[1]),
        "--verbose",
    ]
    
    return [cmd]


def create_symlinks_for_masks(mask_output_dir, image_path, plate_new, config, logger):
    """
    Create symlinks with plate_new names pointing to the mask files with plate_old names.
    """
    pattern_images = config["pattern_images"]
    
    # Get all mask files that were generated
    mask_files = glob.glob(os.path.join(mask_output_dir, pattern_images))
    
    for mask_file in mask_files:
        mask_filename = os.path.basename(mask_file)
        
        # Create symlink in the same directory as the masks but with plate_new name
        # You might need to adjust this logic based on your naming convention
        symlink_path = os.path.join(os.path.dirname(mask_file), f"{plate_new}_{mask_filename}")
        
        try:
            if not os.path.exists(symlink_path):
                os.symlink(mask_file, symlink_path)
                logger.info(f"Created symlink: {symlink_path} -> {mask_file}")
        except OSError as e:
            logger.error(f"Failed to create symlink {symlink_path}: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run segmentation pipeline")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    print(f"Running segmentation with config: {args.config}")
    process_segmentations(args.config)
