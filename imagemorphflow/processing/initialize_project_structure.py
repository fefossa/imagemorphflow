import os
import json
import argparse
from pathlib import Path
from imagemorphflow.utils import file_utils, create_project_structure


def generate_symlink_json(config_path):
    """Generate JSON mapping folders to user-defined plate names."""

    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    config = file_utils.load_config(config_path)
    image_dir = config["image_path"]
    project_name = config["project_name"]
    output_dir_template = config["base_path"]

    output_dir = Path(
        output_dir_template.format(username=username, project_name=project_name)
    )

    project_base_dir = Path(config["project_root"])
    # if not os.path.isdir(project_base_dir):
    create_project_structure.create_project_structure(project_base_dir)

    output_dir = output_dir / "symlinks"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_file = output_dir / config["symlinks_file"]

    if not image_dir or not os.path.exists(image_dir):
        raise FileNotFoundError(f"image_path does not exist: {image_dir}")

    print(f"Scanning folders in: {image_dir}")

    # Get all folders inside the base directory
    folders = file_utils.get_folders_in_path(image_dir)

    # Extract plate names from the folder structure
    plate_names = file_utils.extract_plate_names(folders)

    # Prepare dictionary for JSON
    mappings = {folder: "" for folder in plate_names}  # Empty new names

    # If the JSON file already exists, preserve user inputs
    if os.path.exists(json_file):
        with open(json_file, "r") as f:
            existing_mappings = json.load(f)
        for plate in mappings:
            if plate in existing_mappings and existing_mappings[plate]:
                mappings[plate] = existing_mappings[plate]

    with open(json_file, "w") as f:
        json.dump(mappings, f, indent=4)

    print(f"Symlink mapping file generated: {json_file}")
    print(
        "Please open this file and provide new names for each plate BEFORE running the next step."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create project structure and plate names mapping")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    print(f"Running initialize_project_structure.py with config: {args.config}")
    generate_symlink_json(args.config)
