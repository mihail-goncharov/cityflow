import pytest

from cityflow.ingestion.download import parse_month


@pytest.mark.parametrize("value", ["2025-1", "2025-13", "2025-00", "jan", ""])
def test_parse_month_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_month(value)


@pytest.mark.parametrize("value", ["2025-01", "2025-02", "2025-03"])
def test_parse_month_accepts_valid_value(value):
    assert parse_month(value) == value