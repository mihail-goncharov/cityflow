from cityflow.build_manifest import PROJECT_ROOT
from cityflow.transform.reasons import RejectReason

MEDALLION_DOC = PROJECT_ROOT / "docs" / "medallion.md"


def test_reject_reason_values_are_unique_snake_case() -> None:
    values = [reason.value for reason in RejectReason]

    assert len(values) == len(set(values))


def test_reject_reason_is_a_plain_string_for_parquet() -> None:
    assert RejectReason.FARE_TOO_HIGH == "fare_too_high"
    assert f"{RejectReason.FARE_TOO_HIGH}" == "fare_too_high"


def test_every_reject_reason_is_documented() -> None:
    doc = MEDALLION_DOC.read_text(encoding="utf-8")

    undocumented = [r.value for r in RejectReason if f"`{r.value}`" not in doc]

    assert undocumented == []
