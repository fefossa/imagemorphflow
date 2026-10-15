
import os
import re
import argparse
import xml.etree.ElementTree as ET



# Regex pattern to match only valid XML files (e.g., E5XX-18005_Transfer_1234567890.xml)
valid_xml_pattern = re.compile(r"^E5XX-18005_Transfer_\d+\.xml$")

def extract_protocol_name(xml_file_path):
    """
    Parses the XML file and extracts the text value of the <ProtocolName> element.
    """
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        protocol_element = root.find(".//ProtocolName")
        if protocol_element is not None and protocol_element.text:
            return protocol_element.text.strip()
        else:
            return "ProtocolName not found"
    except Exception as e:
        return f"Error parsing XML: {e}"

def check_folders(base_directory):
    """
    Checks each subfolder in the base directory for exactly 3 valid XML files
    and prints their names and ProtocolName values in alphabetical order.
    """
    for folder_name in os.listdir(base_directory):
        subfolder_path = os.path.join(base_directory, folder_name)
        if not os.path.isdir(subfolder_path):
            continue

        all_files = os.listdir(subfolder_path)
        matching_xml_files = [f for f in all_files if valid_xml_pattern.match(f)]

        print(f"\nChecking folder: {folder_name}")

        # Check if there are exactly 3 matching XML files
        if len(matching_xml_files) != 3:
            print(f"⚠️  Expected 3 valid XML files, but found {len(matching_xml_files)}:")
            for f in matching_xml_files:
                print(f"  - {f}")
            continue

        # Sort the XML files alphabetically
        matching_xml_files.sort()

        # Print ProtocolName for each XML
        for xml_filename in matching_xml_files:
            xml_path = os.path.join(subfolder_path, xml_filename)
            protocol_name = extract_protocol_name(xml_path)
            print(f"{xml_filename} → {protocol_name}")

        return xml_filename, protocol_name

def copy_echo_files():
    raise NotImplementedError("Legacy Echo-copy integration is not implemented; use convert_echo_files")


def get_list_features_for_one_plate(profile_path):
    import pandas as pd
    import pycytominer

    df = pd.read_csv(profile_path, sep="\t")
    return pycytominer.cyto_utils.infer_cp_features(df)


def change_cp3_config_file():
    raise NotImplementedError("Legacy CP3 config generation is not implemented")


def profile_plates():
    raise NotImplementedError("Legacy CP3 profiling is not implemented; use join_profiles")


def annotate_with_cpp():
    raise NotImplementedError("Legacy CP3 annotation is not implemented; use join_profiles")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check XML files and extract ProtocolName values.")
    parser.add_argument("directory", help="Path to the main directory containing subfolders with XML files.")
    args = parser.parse_args()

    check_folders(args.directory)
