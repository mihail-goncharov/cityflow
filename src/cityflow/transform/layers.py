from typing import Literal

from cityflow.ingestion.download import parse_month
from cityflow.ingestion.manifest import build_manifest_key

Layer = Literal["bronze", "silver", "quarantine"]

DATASET_PATH = "nyc_tlc/yellow_taxi"
DATA_FILENAME = "yellow_tripdata.parquet"
QUALITY_SUMMARY_FILENAME = "quality_summary.json"


def build_layer_folder(layer: Layer, month: str) -> str:
    """Return the folder of one layer for one month, without a trailing slash."""
    year, month_number = parse_month(month).split("-")
    return f"{layer}/{DATASET_PATH}/year={year}/month={month_number}"


def build_layer_key(layer: Layer, month: str) -> str:
    """Return the key of the single Parquet data object of a layer and month.

    The month is only in the folder name, so the two cannot disagree.
    """
    return f"{build_layer_folder(layer, month)}/{DATA_FILENAME}"


def build_layer_manifest_key(layer: Layer, month: str) -> str:
    """Return the key of the layer's manifest, next to its data object."""
    return build_manifest_key(build_layer_key(layer, month))


def build_quality_summary_key(month: str) -> str:
    """Return the key of the quality summary, stored in the Silver folder."""
    return f"{build_layer_folder('silver', month)}/{QUALITY_SUMMARY_FILENAME}"
