"""Build image metadata with portable, optional directory links."""

import argparse
import glob
import os
from pathlib import Path

from imagemorphflow.portable import image_directory
from imagemorphflow.utils import file_utils, load_data_utils


def generate_load_data(config_path):
    config = file_utils.load_config(config_path)
    workspace = Path(config["base_path"])
    logger = file_utils.setup_logging(config, base_path=workspace, pipeline="load_data")
    microscope = config["microscopes"].get(config["microscope"])
    if not microscope:
        raise ValueError(f"Unknown microscope: {config['microscope']}")
    mappings = file_utils.load_symlink_mappings(workspace / "symlinks" / config["symlinks_file"])
    images = Path(config["scratch_image_path"] if config.get("use_scratch") else config["image_path"])
    masks = config.get("masks", {})
    for original, plate in mappings.items():
        pattern = microscope["input_folder_pattern"].format(image_dir=images, plate_old=original)
        if glob.has_magic(pattern):
            candidates = [Path(path) for path in glob.glob(pattern) if Path(path).is_dir()]
            if not candidates:
                raise FileNotFoundError(f"No matching acquisition folders: {pattern}")
            source = max(candidates, key=lambda path: (path.stat().st_mtime_ns, str(path)))
            # Preserve the existing acquisition layout underneath the plate folder.
            suffix = source.relative_to(images / original)
        else:
            source, suffix = Path(pattern), Path()
        destination = Path(config["image_local_path"].format(plate_new=plate)) / suffix
        actual = image_directory(source, destination, config.get("image_link_mode", "auto"))
        mask_output = masks.get("mask_output_dir")
        load_data_utils.generate_load_data(
            logger, str(source), config["channels"],
            regex_image=microscope["regex_image"], regex_plate=microscope["regex_plate"],
            output_dir_bool=True, output_dir=str(workspace / "loaddata" / plate),
            cluster=True, cluster_img_folder=str(actual),
            cluster_illum_folder=config["illum_out_path"].format(plate_new=plate),
            provide_plate_name=True, plate_name=plate,
            include_masks=masks.get("include_masks", False), mask_channels=masks.get("mask_channels", {}),
            mask_output_dir=mask_output.format(plate_new=plate) if mask_output else None,
            segmentation_method=masks.get("segmentation_method"),
        )
        logger.info("Load data for %s reads images from %s", plate, actual)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    generate_load_data(parser.parse_args().config)
