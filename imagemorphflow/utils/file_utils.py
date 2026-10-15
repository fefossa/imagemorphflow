from imagemorphflow.config import load_config, load_mappings as load_symlink_mappings
import os
import re
import sys
import json
import shutil
import numpy as np
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def get_folders_in_path(path):
    """
    Get all folders inside a directory
    """
    # List all directories in the provided path
    folders = [
        os.path.join(path, folder)
        for folder in os.listdir(path)
        if os.path.isdir(os.path.join(path, folder))
    ]
    print("found those folders", folders)
    return folders


def extract_plate_names(folders, regex_plate=".*[\\/](?P<Plate>.*)"):
    """
    Extract plate names assuming that inside a folder, the name of the folders are the plate name. Save those and pass it to create_plate_dict.
    """
    plate_names = []
    pattern = re.compile(regex_plate)
    for folder in folders:
        match = pattern.match(folder)
        if match:
            plate_names.append(match.group("Plate"))
    return sorted(plate_names)


def create_plate_dict(plate_names):
    """
    Create plate_dict when there is no links.sh file to get those plate names from.
    """
    plate_dict = {}
    for plate in plate_names:
        value = input(f"Enter value for {plate}: ")
        plate_dict[plate] = value
    return plate_dict


def load_and_resize_image(img_path, target_size_x, target_size_y):
    try:
        img = Image.open(img_path) #convert("L")  # Grayscale
        img_resized = img.resize((target_size_x, target_size_y), Image.LANCZOS)

        np_img = np.array(img_resized)
        print(f"[{os.path.basename(img_path)}] min={np_img.min()}, max={np_img.max()}")

        return img_resized
    except Exception as e:
        print(f"Error loading image {img_path}: {e}")
        return Image.new("L", (target_size_x, target_size_y), color=255)


def stretch_contrast(img, low, high, skip_contrast, microscope, ov):
    """
    - Se skip_contrast=True: escala linear full-range (min→0, max→255).
    - Senão: clipa entre low/high (na escala original) e então reescalona para 0–255.
    """
    # converte pra float para não perder precisão
    np_raw = np.array(img)
    np_img = np.array(img, dtype=float)
    img_min, img_max = np_img.min(), np_img.max()
    
    if img_max == img_min:
        return Image.fromarray(np.zeros_like(np_img, dtype=np.uint8))

    # bit_type=np_raw.dtype
    # if np_img.dtype == np.uint8:
    #     bit_depth = 255.0
    # elif np_img.dtype == np.uint16:
    #     bit_depth = 4095.0
    # else:
    #     bit_depth = img_max
    #     print(bit_type)

    if microscope == "endeavor":
        bit_depth = 4095.0
    elif microscope == "imagexpress":
        bit_depth = 65535.0
    else:
        bit_type=np_raw.dtype
        bit_depth=255.0
        print(f"The bit depth is {bit_type}, assuming 255 values of gray. Check code.")

    if ov == "plates":
        scaled = (np_img / bit_depth) * 255.0
    else: 
        scaled = np_img

    if skip_contrast:
        out = np.clip(scaled, 0, 255)
    else:
        clipped = np.clip(np_img, low, high)
        out = (clipped - low) * (255.0 / (high - low))
        # out = ((np_img - img_min)) / ((img_max - img_min)) * 255.0 #from stack over flow

    return Image.fromarray(out.astype(np.uint8))


def draw_text(img, text, position, font_path, font_size=30):
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)
    draw.text(position, text, font=font, fill=(255))  # White text
    return img


def normalize_site(site, microscope, num_sites_x=4, num_sites_y=4):
    if microscope == "endeavor" and not (num_sites_x == 1 and num_sites_y == 1):
        return {"3": "1", "4": "2", "1": "3", "2": "4"}.get(site, site)
    return site


def get_num_cores(fraction=0.8):
    total_cores = os.cpu_count() or 1
    return max(1, int(total_cores * fraction))


def setup_logging(config, base_path, pipeline="no_name"):
    log_dir = os.path.join(base_path, "logs", pipeline)
    os.makedirs(log_dir, exist_ok=True)
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    error_log_path = os.path.join(log_dir, f"{current_time}_errors.log")

    logging.basicConfig(
        filename=error_log_path,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger = logging.getLogger("error_logger")
    logger.info(f"microscope: {config.get('microscope', 'not set')}")
    logger.info(f"image_path: {config.get('image_path', 'not set')}")
    logger.info(f"symlinks_file: {config.get('symlinks_file', 'not set')}")

    def handle_uncaught_exceptions(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Let KeyboardInterrupt exit normally without logging error
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_uncaught_exceptions

    return logger


def create_symlinks(image_dir, json_file, images_folder_symlink):
    """Create symlinks based on user-defined mappings from JSON."""

    if not image_dir or not os.path.exists(image_dir):
        print(
            f"Error: image_path '{image_dir}' does not exist! Check your config.yaml."
        )
        return

    # Load mappings from JSON
    with open(json_file, "r") as f:
        mappings = json.load(f)

    for src, dest_name in mappings.items():
        if not src or not dest_name:
            print(f"Skipping empty mapping: {src} → {dest_name}")
            continue

        src_path = os.path.join(image_dir, src)
        dest_path = os.path.join(images_folder_symlink, dest_name)

        if not os.path.exists(src_path):
            print(f"Source folder '{src_path}' does not exist. Skipping.")
            continue

        if os.path.exists(dest_path):
            if os.path.islink(dest_path):
                if os.readlink(dest_path) == src_path:
                    continue
                os.remove(dest_path)
            else:
                continue  # Skip if it's not a symlink

        try:
            os.symlink(src_path, dest_path)
            print(f"Created symlink: {dest_path} → {src_path}")
        except OSError as error:
            raise OSError(f"Could not create symlink {dest_path} -> {src_path}") from error


def get_project_base_dir(project_name):
    return Path.home() / "projects" / project_name


def copy_folder_contents(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            if dest_item.exists():
                print(f"Directory exists, skipping: {dest_item}")
            else:
                shutil.copytree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)

def find_deepest_image_folder(base_folder):
    for dirpath, dirnames, filenames in os.walk(base_folder):
        if any(f.endswith((".tif", ".tiff", ".TIFF")) and "thumb" not in f for f in filenames):
            return Path(dirpath)
    return base_folder
