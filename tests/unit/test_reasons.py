import re

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


def documented_reason_codes() -> set[str]:
    """Reason codes in the first column of the reject rule table (section 7.1)."""
    doc = MEDALLION_DOC.read_text(encoding="utf-8")
    section = doc.split("### 7.1 Reject rules")[1].split("### 7.2")[0]
    codes: set[str] = set()
    for line in section.splitlines():
        if line.startswith("| `"):
            first_cell = line.split("|")[1]
            codes.update(re.findall(r"`([a-z_]+)`", first_cell))
    return codes


def test_reject_rule_table_lists_exactly_the_enum_codes() -> None:
    # The other direction of the test above: a code documented in the table
    # but missing from the enum would never appear in Quarantine.
    assert documented_reason_codes() == {reason.value for reason in RejectReason}
