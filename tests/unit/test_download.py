import pytest

from cityflow.ingestion.download import build_source_url, parse_month


@pytest.mark.parametrize("value", ["2025-1", "2025-13", "2025-00", "jan", ""])
def test_parse_month_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_month(value)


@pytest.mark.parametrize("value", ["2025-01", "2025-02", "2025-03"])
def test_parse_month_accepts_valid_value(value):
    assert parse_month(value) == value


def test_build_source_url_january_2025():
    assert (build_source_url("2025-01") ==
            "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet")