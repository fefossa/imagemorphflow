from contextlib import closing
# utils/join_profiles_utils.py
import os
import sqlite3
import pandas as pd
try:
    import pycytominer
    from pycytominer.cyto_utils.cells import SingleCells
except ImportError:
    pycytominer = None
    SingleCells = None
from pathlib import Path

COUNT_OBJECT_COL = "Count_Cells"  # Override with join.count_object_column.

def require_profiles():
    if pycytominer is None:
        raise ImportError("Profile processing requires: pip install 'imagemorphflow[profiles]'")


def get_image_cols_from_db(
    database_path,
    count_obj_col=COUNT_OBJECT_COL,
    image_feature_categories=None,
):
    image_feature_categories = image_feature_categories or []

    with closing(sqlite3.connect(database_path)) as conn:
        image_table_cols = pd.read_sql("PRAGMA table_info(Image);", conn)["name"].tolist()

    base_cols = [
        "TableNumber",
        "ImageNumber",
        "Metadata_Site",
        count_obj_col,
    ]

    category_cols = [
        col for col in image_table_cols
        if any(col.startswith(f"{category}_") for category in image_feature_categories)
    ]

    image_cols = [
        col for col in base_cols + category_cols
        if col in image_table_cols
    ]

    return list(dict.fromkeys(image_cols))

def rename_metadata_columns(database_path):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    tables = ["Cells", "Nuclei", "Cytoplasm"]
    old_cols = ["Metadata_Plate", "Metadata_Site", "Metadata_Well"]

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1] for row in cursor.fetchall()]
        for col in old_cols:
            old = f"{table}_{col}"
            if old in columns:
                cursor.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {col};")
                print(f"Renamed {old} → {col} in {table}")

    conn.commit()
    conn.close()


def clean_metadata_cols(df):
    import re

    pattern = r"Metadata_(Plate|Site|Well)(_[a-zA-Z]*)?"
    seen = set()
    rename_map = {}
    to_drop = []

    for col in df.columns:
        match = re.match(pattern, col)
        if match:
            base = match.group(1)
            if base not in seen:
                seen.add(base)
                rename_map[col] = f"Metadata_{base}"
            else:
                to_drop.append(col)

    df = df.rename(columns=rename_map).drop(columns=to_drop)
    return df

def get_sql_table_names(database_path):
    with closing(sqlite3.connect(database_path)) as conn:
        tables = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table';",
            conn,
        )["name"].tolist()

    return tables


def read_table(database_path, table_name):
    with closing(sqlite3.connect(database_path)) as conn:
        df = pd.read_sql('SELECT * FROM "' + table_name.replace('"', '""') + '";', conn)

    return df

def merge_extra_channel_tables(
    df,
    database_path,
    extra_channels,
    compartments_found,
):
    table_names = set(get_sql_table_names(database_path))
    df_merged = df.copy()

    compartment_table_map = {
        "cells": "Cells",
        "cytoplasm": "Cytoplasm",
        "nuclei": "Nuclei",
    }

    object_key_map = {
        "cells": "Cells_Number_Object_Number",
        "cytoplasm": "Cytoplasm_Number_Object_Number",
        "nuclei": "Nuclei_Number_Object_Number",
    }

    for compartment in compartments_found:
        base_table = compartment_table_map[compartment]
        object_key = object_key_map[compartment]

        for channel in extra_channels:
            extra_table = f"{base_table}_{channel}_extra"

            if extra_table not in table_names:
                print(f"Extra table not found, skipping: {extra_table}")
                continue

            df_extra = read_table(database_path, extra_table)

            table_key_candidates = [
                "Image_TableNumber",
                "Metadata_TableNumber",
                "TableNumber",
            ]

            left_table_key = next(
                (col for col in table_key_candidates if col in df_merged.columns),
                None,
            )

            if left_table_key is None:
                raise ValueError(
                    "Could not find TableNumber key in merged SingleCells dataframe. "
                    f"Available TableNumber columns: {[c for c in df_merged.columns if 'TableNumber' in c]}"
                )

            df_extra = df_extra.rename(
                columns={
                    "TableNumber": left_table_key,
                    "ImageNumber": "Metadata_ImageNumber",
                    "ObjectNumber": object_key,
                }
            )

            merge_keys = [
                left_table_key,
                "Metadata_ImageNumber",
                object_key,
            ]

            missing_keys = [
                col for col in merge_keys
                if col not in df_merged.columns or col not in df_extra.columns
            ]

            if missing_keys:
                raise ValueError(
                    f"Missing merge keys for {extra_table}: {missing_keys}"
                )

            feature_cols = [
                col for col in df_extra.columns
                if col not in merge_keys
                and not col.startswith("Metadata_")
            ]

            df_merged = df_merged.merge(
                df_extra[merge_keys + feature_cols],
                on=merge_keys,
                how="left",
                validate="many_to_one",
            )

            print(f"Merged {extra_table}: {len(feature_cols)} extra columns")

    return df_merged


def merge_innercells_features(df, database_path):
    table_names = set(get_sql_table_names(database_path))

    if "InnerCells" not in table_names:
        print("InnerCells table not found, skipping.")
        return df

    df_inner = read_table(database_path, "InnerCells")

    table_key_candidates = [
        "Image_TableNumber",
        "Metadata_TableNumber",
        "TableNumber",
    ]

    left_table_key = next(
        (
            col
            for col in table_key_candidates
            if col in df.columns
        ),
        None,
    )

    if left_table_key is None:
        raise ValueError(
            "Could not find TableNumber key in SingleCells dataframe."
        )

    required_cols = [
        "TableNumber",
        "ImageNumber",
        "ObjectNumber",
        "InnerCells_Math_GFPDelta",
    ]

    missing_cols = [
        col
        for col in required_cols
        if col not in df_inner.columns
    ]

    if missing_cols:
        raise ValueError(
            f"Missing InnerCells columns: {missing_cols}"
        )

    df_inner = df_inner[required_cols].rename(
        columns={
            "TableNumber": left_table_key,
            "ImageNumber": "Metadata_ImageNumber",
            "ObjectNumber": "Cells_Number_Object_Number",
        }
    )

    merge_keys = [
        left_table_key,
        "Metadata_ImageNumber",
        "Cells_Number_Object_Number",
    ]

    df = df.merge(
        df_inner,
        on=merge_keys,
        how="left",
        validate="one_to_one",
    )

    print(
        "Merged InnerCells_Math_GFPDelta into SingleCells: "
        f"{df['InnerCells_Math_GFPDelta'].notna().sum():,}/"
        f"{len(df):,} cells with values"
    )

    return df


def join_and_aggregate(
    project_path,
    plate,
    project_name,
    write_parquet=False,
    count_obj_col=COUNT_OBJECT_COL,
    extra_channels=None,
    options=None,
):
    require_profiles()
    options = options or {}
    count_obj_col = options.get("count_object_column", count_obj_col)
    plate_db_path = os.path.join(project_path, "backend", plate, f"{plate}.db")
    if not Path(plate_db_path).is_file():
        raise FileNotFoundError(f"Plate database missing: {plate_db_path}")
    db_uri = f"sqlite:///{plate_db_path}"
    output_dir = os.path.join(project_path, "analysis", plate)
    profile_dir = os.path.join(project_path, "profiles", plate)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(profile_dir, exist_ok=True)

    if options.get("rename_metadata", False):
        rename_metadata_columns(plate_db_path)
    image_feature_categories = options.get("image_feature_categories", ["ImageQuality", "Count", "TableNumber", "ImageNumber", "Math"])
    strata_agg = options.get("strata", ["Metadata_Plate", "Metadata_Well", "Metadata_Site"])
    tables = set(get_sql_table_names(plate_db_path))
    compartments_found = [name.lower() for name in ("Cells", "Cytoplasm", "Nuclei") if name in tables]
    if not compartments_found:
        raise ValueError(f"No cell compartments in {plate_db_path}")

    image_cols = get_image_cols_from_db(
        plate_db_path,
        count_obj_col=count_obj_col,
        image_feature_categories=image_feature_categories,
    )

    single_cells = SingleCells(
        db_uri,
        image_cols=image_cols,
        add_image_features=False,
        image_feature_categories=image_feature_categories,
        compartments=compartments_found,
    )
    df = single_cells.merge_single_cells()

    if options.get("clean_metadata", False):
        df = clean_metadata_cols(df)

    df = merge_innercells_features(df=df, database_path=plate_db_path)

    print(
        "GFPDelta columns before parquet:",
        [col for col in df.columns if "GFPDelta" in col]
    )

    if write_parquet:
        df.to_parquet(
            os.path.join(profile_dir, "SingleCells.parquet"),
            compression="snappy",
            index=False,
        )

    feat_cols = pycytominer.cyto_utils.infer_cp_features(df, image_features=True)
    feat_cols.insert(0, count_obj_col)
    feat_cols.insert(0, "Metadata_ImageNumber")

     # CHeck if extra cols exist; if yes, they're carried for the final profile.
    extra_image_features = [
        col
        for col in df.columns
        if (
            col.startswith("Math_")
            or col.startswith("Count_")
        )
        and pd.api.types.is_numeric_dtype(df[col])
        and col not in feat_cols
    ]
    
    feat_cols = extra_image_features + feat_cols
    print("Math/Binuclei in feat_cols:", [c for c in feat_cols if "Math" in c or "Binuclei" in c])

    df_agg = pycytominer.aggregate(
        df,
        strata=strata_agg,
        operation="median",
        features=feat_cols,
    )
    df_agg["Metadata_Count_Cells"] = df_agg[count_obj_col]
    df_agg.to_csv(os.path.join(profile_dir, "Results.tsv"), sep="\t", index=False)
    
    extra_channels = extra_channels or []

    if extra_channels:
        print("Extra channels enabled:", extra_channels)
        print("df shape before extra merge:", df.shape)
        print("df columns with TableNumber:", [c for c in df.columns if "TableNumber" in c])
        print("df columns with ImageNumber:", [c for c in df.columns if "ImageNumber" in c])
        print("df columns with Object_Number:", [c for c in df.columns if "Object_Number" in c])
        df_extra = merge_extra_channel_tables(
            df=df,
            database_path=plate_db_path,
            extra_channels=extra_channels,
            compartments_found=compartments_found,
        )

        feat_cols_extra = pycytominer.cyto_utils.infer_cp_features(
            df_extra,
            image_features=True,
        )
        feat_cols_extra.insert(0, count_obj_col)
        feat_cols_extra.insert(0, "Metadata_ImageNumber")

        df_agg_extra = pycytominer.aggregate(
            df_extra,
            strata=strata_agg,
            operation="median",
            features=feat_cols_extra,
        )

        df_agg_extra["Metadata_Count_Cells"] = df_agg_extra[count_obj_col]

        df_agg_extra.to_csv(
            os.path.join(profile_dir, "Results_extra.tsv"),
            sep="\t",
            index=False,
        )

    # img_cols = [c for c in df_agg.columns if "ImageQuality" in c or c.startswith("Metadata_")]
    # df_img = df_agg[img_cols]
    # df_img.to_csv(os.path.join(profile_dir, "Image.tsv"), sep="\t", index=False)

    return profile_dir, df_agg


def get_features_and_metadata(df, image_features=True):
    require_profiles()

    features = pycytominer.cyto_utils.features.infer_cp_features(
        df, metadata=False, image_features=image_features
    )
    get_meta_cols = df.drop(columns=features)
    metadata = list(get_meta_cols.columns)

    return features, metadata


def annotate(df, platemap, profile_dir):
    require_profiles()

    df_annot = pycytominer.annotate(
        profiles=df,
        platemap=platemap,
        join_on=["Metadata_well_position", "Metadata_Well"],
    )
    df_annot.to_csv(
        os.path.join(profile_dir, "Results_agg_annot.tsv"), sep="\t", index=False
    )

    return df_annot


def normalize(df, features, metadata, profile_dir, normalize_to_negcon=True):
    require_profiles()

    if normalize_to_negcon:
        normalize_to = "Metadata_Control_type == 'negcon'"
        out_file = "Results_agg_annot_norm_to_negcon"
    else:
        normalize_to = "all"
        out_file = "Results_agg_annot_norm"

    df_norm = pycytominer.normalize(
        df,
        method="mad_robustize",
        mad_robustize_epsilon=0,
        samples=normalize_to,
        meta_features=metadata,
        features=features,
    )

    df_norm.to_csv(os.path.join(profile_dir, f"{out_file}.tsv"), sep="\t", index=False)

    return df_norm, out_file


def feature_selection(df, features, profile_dir, filename, logger):
    require_profiles()

    df_selected = pycytominer.feature_select(
        df,
        features=features,
        operation=[
            "correlation_threshold",
            "variance_threshold",
            "drop_na_columns",
            "drop_outliers",
        ],
        corr_threshold=0.95,
    )

    num_removed = df.shape[1] - df_selected.shape[1]
    logger.info(f"Number of columns removed: {num_removed}")
    logger.info(f"Number of features before selection: {len(features)}")
    percentage_removed = 100 - (df_selected.shape[1] * 100) / df.shape[1]
    logger.info(f"Percentage of removed columns: {percentage_removed:.2f}%")

    df_selected.to_csv(
        os.path.join(profile_dir, f"{filename}_allplates_featsel.tsv"),
        sep="\t",
        index=False,
    )
