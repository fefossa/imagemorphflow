import os
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from imagemorphflow.utils import predict_masks_utils, file_utils


def process_segmentations(config_path):
    config = file_utils.load_config(config_path)
    image_path_template = config["image_local_path"]
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    output_dir_template = config["base_path"]

    num_cores = int(config.get("mask_workers", 1))

    masks_config = config.get("masks", {})
    mask_output_dir_template = masks_config.get("mask_output_dir", None)

    logger = predict_masks_utils.setup_logging(
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
    symlink_mappings = file_utils.load_symlink_mappings(json_file)

    failed = []
    with ThreadPoolExecutor(max_workers=num_cores) as executor:
        futures = {}
        for plate_old, plate_new in symlink_mappings.items():
            mask_output_dir = mask_output_dir_template.format(
                username=username,
                project_name=config["project_name"],
                plate_new=plate_new,
            )
            image_path = image_path_template.format(
                username=username,
                project_name=config["project_name"],
                plate_new=plate_new,
            )
            commands = predict_masks_utils.generate_segmentation_command(
                image_path, mask_output_dir, plate_new, config
            )
            if not commands:
                raise ValueError(f"No images found for segmentation in {image_path}")
            for cmd in commands:
                futures[executor.submit(predict_masks_utils.run_segmentation, cmd)] = (
                    cmd
                )

        for future in as_completed(futures):
            if not future.result():
                failed.append(futures[future])
                logger.error(f"Failed: {' '.join(futures[future])}")

    # Retry failed commands
    persistent_failures = []
    for cmd in failed:
        logger.info(f"Retrying failed command: {' '.join(cmd)}")
        if not predict_masks_utils.run_segmentation(cmd):
            persistent_failures.append(cmd)
    if persistent_failures:
        raise RuntimeError(f"{len(persistent_failures)} segmentation commands failed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run segmentation pipeline")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    print(f"Running segmentation with config: {args.config}")
    process_segmentations(args.config)
