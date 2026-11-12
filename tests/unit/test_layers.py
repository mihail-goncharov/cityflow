import pytest

from cityflow.ingestion.pipeline import build_object_key
from cityflow.transform.layers import (
    build_layer_folder,
    build_layer_key,
    build_layer_manifest_key,
    build_quality_summary_key,
)

MONTH = "2025-01"


@pytest.mark.parametrize("layer", ["bronze", "silver", "quarantine"])
def test_build_layer_key_uses_layer_prefix_and_month_folder(layer: str) -> None:
    assert build_layer_key(layer, MONTH) == (
        f"{layer}/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata.parquet"
    )


def test_build_layer_folder_matches_raw_folder_except_for_prefix() -> None:
    raw_key = build_object_key(MONTH, "yellow_tripdata_2025-01.parquet")
    raw_folder = raw_key.rsplit("/", 1)[0]

    assert build_layer_folder("bronze", MONTH) == raw_folder.replace(
        "raw/", "bronze/", 1
    )


def test_build_layer_key_filename_is_the_same_for_every_month() -> None:
    assert build_layer_key("silver", "2025-01").rsplit("/", 1)[1] == (
        build_layer_key("silver", "2025-02").rsplit("/", 1)[1]
    )


def test_build_layer_key_keeps_two_digit_month() -> None:
    assert "month=03" in build_layer_key("silver", "2025-03")


def test_build_layer_key_rejects_invalid_month() -> None:
    with pytest.raises(ValueError, match="expected YYYY-MM"):
        build_layer_key("silver", "2025-13")


def test_build_layer_folder_has_no_trailing_slash() -> None:
    assert build_layer_folder("quarantine", MONTH) == (
        "quarantine/nyc_tlc/yellow_taxi/year=2025/month=01"
    )


def test_build_layer_manifest_key_is_next_to_data_object() -> None:
    assert build_layer_manifest_key("silver", MONTH) == (
        "silver/nyc_tlc/yellow_taxi/year=2025/month=01/manifest.json"
    )


def test_build_quality_summary_key_is_in_silver_folder() -> None:
    assert build_quality_summary_key(MONTH) == (
        "silver/nyc_tlc/yellow_taxi/year=2025/month=01/quality_summary.json"
    )
