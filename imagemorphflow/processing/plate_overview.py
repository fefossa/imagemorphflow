from imagemorphflow.portable import plate_image_directory
import os
import re
import argparse
from multiprocessing import Pool
from PIL import Image, ImageDraw
from pathlib import Path
from imagemorphflow.utils import file_utils

def get_img_pos(metadata, config):
    """Calculate the position of an image based on metadata."""
    well = metadata["Well"]
    row_letter = well[0]  # 'C'
    column_number = int(well[1:])  # 6

    row = ord(row_letter.upper()) - ord("A")
    # row = ord(row_number) - 65
    column = column_number - 1
    site = int(metadata["Site"]) - 1

    x = (
        column
        * config["image_config"]["target_size_x"]
        * config["image_config"]["num_sites_x"]
    )
    y = (
        row
        * config["image_config"]["target_size_y"]
        * config["image_config"]["num_sites_y"]
    )

    site_offset_x = (site % config["image_config"]["num_sites_x"]) * config[
        "image_config"
    ]["target_size_x"]
    site_offset_y = (site // config["image_config"]["num_sites_y"]) * config[
        "image_config"
    ]["target_size_y"]

    return x + site_offset_x, y + site_offset_y, row, column, site


def draw_plate_grid(
    img,
    img_width,
    img_height,
    target_size_x,
    target_size_y,
    num_sites_x,
    num_sites_y,
    well_rows=16,
    well_cols=24,
):
    """Draw grid lines for the plate wells."""
    well_width = target_size_x * num_sites_x
    well_height = target_size_y * num_sites_y
    draw = ImageDraw.Draw(img)
    # Horizontal lines
    for r in range(1, well_rows):
        y = r * well_height
        draw.line([(0, y), (img_width, y)], fill=200)
    # Vertical lines
    for c in range(1, well_cols):
        x = c * well_width
        draw.line([(x, 0), (x, img_height)], fill=200)


def generate_plate_overview(config, input_images, plate_overview_output, channel, ov):
    """Generate the plate overview image."""
    # Config values
    ic = config["image_config"]
    microscope = config["microscope"]
    regex_image = config["microscopes"][microscope]["regex_image"]

    ic["num_sites_x"] = config["microscopes"][microscope].get("num_sites_x", ic["num_sites_x"])
    ic["num_sites_y"] = config["microscopes"][microscope].get("num_sites_y", ic["num_sites_y"])

    tx, ty = ic["target_size_x"], ic["target_size_y"]
    nx, ny = ic["num_sites_x"], ic["num_sites_y"]
    low, high, add = (
        ic["intensity_cutoff_low"],
        ic["intensity_cutoff_high"],
        ic["intensity_addition"],
    )

    # Prepare the output image
    img_width = tx * 24 * nx
    img_height = ty * 16 * ny
    img = Image.new("L", (img_width, img_height), color=0)  # White background

    # Load font for text
    font_path = config.get(
        "font_path", "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf"
    )

    # Image files
    input_images = Path(input_images)
    image_extensions = list(Image.registered_extensions().keys())
    is_recursive = config["microscopes"][microscope].get("recursive", False)

    if is_recursive:
        image_files = [
            str(f) for f in input_images.rglob("*")
            if f.is_file() and f.suffix.lower() in image_extensions
        ]
    else:
        image_files = [
            str(f) for f in input_images.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        ]

    if not image_files:
        print(f"⚠️ No image files found in {input_images} with specified extensions.")

    # attemp to strech contrast based on well intensity
    # need to implement logic on strech_constrast
    # well_images = defaultdict(list)
    # for img_path in image_files:
    #     match = re.search(regex_image, img_path)
    #     if not match:
    #         continue
    #     metadata = match.groupdict()
    #     well = metadata["Well"]
    #     well_images[well].append(img_path)
    any_added = False
    for img_path in image_files:
        # Extract metadata from the file name
        match = re.search(regex_image, img_path)
        if not match:
            continue

        metadata = match.groupdict()
        metadata["Site"] = file_utils.normalize_site(
            metadata["Site"],
            microscope,
            ic["num_sites_x"],
            ic["num_sites_y"],
        )

        if str(channel) != str(metadata.get("Channel")):
            continue

        any_added = True
        img_x, img_y, row, column, site = get_img_pos(metadata, config)

        img_tile = file_utils.load_and_resize_image(img_path, tx, ty)

        skip_contrast = config["image_config"]["skip_contrast_enhancement"]
        img_tile = file_utils.stretch_contrast(
            img_tile,
            low,
            high + add,
            skip_contrast,
            microscope,
            ov
        )

        img.paste(img_tile, (img_x, img_y))

        if metadata["Site"] == "1":
            well_id = f"{metadata['Well']}"
            img = file_utils.draw_text(img, well_id, (img_x + 5, img_y + 5), font_path)

    if not any_added:
        print(f"⚠️ No image found for {channel}")
        return

    draw_plate_grid(img, img_width, img_height, tx, ty, nx, ny)
    output_image = plate_overview_output / f"{channel}.png"
    img.save(output_image)
    print(f"Plate overview saved to {plate_overview_output}")


def main(config_path):
    """Main entry point to generate the plate overview."""
    config = file_utils.load_config(config_path)

    image_path_template = config["image_local_path"]
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    output_dir_template = config["base_path"]

    output_dir = Path(
        output_dir_template.format(
            username=username, project_name=config["project_name"]
        )
    )
    json_file = output_dir / "symlinks" / config["symlinks_file"]
    symlink_mappings = file_utils.load_symlink_mappings(json_file)

    common_channels = [
        ch
        for ch, name in config.get("channels", {}).items()
        if not str(name).startswith("#")
    ]

    jobs = []
    for plate_old, plate_new in symlink_mappings.items():
        for channel in common_channels:
            for ov in config["overview_types"]:
                input_images = str(plate_image_directory(config, plate_new))
                if "plates" in ov:
                    plate_overview_output = (
                        output_dir / "plate_overview" / "plates" / plate_new
                    )
                else:
                    input_images = re.sub(r"(.*?/images/)(images)", rf"\1{ov}", input_images)
                    plate_overview_output = (
                        output_dir / "plate_overview" / ov / plate_new
                    )

                plate_overview_output.mkdir(parents=True, exist_ok=True)

                jobs.append((config, input_images, plate_overview_output, channel, ov))

                # generate_plate_overview(
                #     config, input_images, plate_overview_output, channel, ov
                # )
    n_workers = file_utils.get_num_cores()
    with Pool(processes=n_workers) as pool:
        pool.starmap(generate_plate_overview, jobs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a plate overview image.")
    parser.add_argument(
        "--config", type=str, required=True, help="Path to the config file"
    )
    args = parser.parse_args()
    print(f"Running plate_overview.py with config: {args.config}")
    main(args.config)
