import os
import shutil
import argparse
import json
import logging
from pathlib import Path
from imagemorphflow.utils import file_utils, create_project_structure


def copy_image_folders_to_scratch(config_path):
    config = file_utils.load_config(config_path)

    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    output_dir_template = config["base_path"]
    output_dir = Path(
        output_dir_template.format(
            username=username, project_name=config["project_name"]
        )
    )

    logger = file_utils.setup_logging(
        config, base_path=output_dir, pipeline="copy_images"
    )

    if not config.get("use_scratch", False):
        logger.info("Config does not request use of scratch. Skipping copy.")
        return

    image_dir = Path(config["image_path"])
    scratch_path = Path(config["scratch_image_path"])
    json_file = output_dir / "symlinks" / config["symlinks_file"]

    if not json_file.exists():
        raise FileNotFoundError(f"Symlink mapping file not found: {json_file}")

    # Load mapping
    mappings = file_utils.load_symlink_mappings(json_file)

    # image_dir_scratch = scratch_base_path / "images" / "images"
    for plate_old, plate_new in mappings.items():
        source_folder = image_dir / plate_old
        relative_path = source_folder.relative_to(image_dir)
        # target_folder = image_dir_scratch / dest
        target_folder = scratch_path / relative_path
        temp_target_folder = scratch_path / (str(relative_path) + ".tmp")

        if not source_folder.exists():
            raise FileNotFoundError(f"Source folder not found: {source_folder}")

        if target_folder.exists():
            logger.info(f"Already copied: {target_folder}")
            continue

        if temp_target_folder.exists():
            logger.info(f"Removing incomplete temp folder: {temp_target_folder}")
            shutil.rmtree(temp_target_folder)

        try:
            logger.info(f"Copying {source_folder} → {temp_target_folder}")
            file_utils.copy_folder_contents(source_folder, temp_target_folder)

            temp_target_folder.rename(target_folder)
            logger.info(f"Copy complete: {target_folder}")
        except Exception as e:
            logger.info(f"Failed to copy {source_folder} → {target_folder}: {e}")
            if temp_target_folder.exists():
                logger.info(f"Cleaning up temp folder due to failure: {temp_target_folder}")
                shutil.rmtree(temp_target_folder)
            raise RuntimeError(f"Failed to copy {source_folder}") from e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy image folders to /mnt/scratch")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    copy_image_folders_to_scratch(args.config)
