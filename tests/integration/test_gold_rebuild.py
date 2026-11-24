"""Rebuild the Gold marts with real dbt and DuckDB (docs/gold.md section 6).

Runs `dbt build` on the Silver fixture, so it needs neither RustFS nor the real
dataset. It checks that building twice on the same input gives the same marts
without duplicates, and that a build replaces the marts instead of adding to them.
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from cityflow.gold.fixture import silver_root, write_silver_fixture

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "dbt"

# The grain of every mart: the columns that must be unique.
MART_KEYS = {
    "mart_daily_trips": ["pickup_date"],
    "mart_hourly_demand": ["pickup_date", "pickup_hour"],
    "mart_pickup_zone_daily": ["pickup_date", "pickup_location_id"],
}
# Rows per mart for the nine fixture trips, counted by hand from docs/gold.md
# section 5: two dates, five date-and-hour pairs, five date-and-zone pairs.
FIXTURE_ROWS = {
    "mart_daily_trips": 2,
    "mart_hourly_demand": 5,
    "mart_pickup_zone_daily": 5,
}


def dbt_build(work_dir: Path, fixture_dir: Path, database: Path) -> None:
    """Run `dbt build` on the fixture in fixture_dir and fail with its output."""
    env = {
        **os.environ,
        "CITYFLOW_SILVER_ROOT": str(silver_root(fixture_dir)),
        "CITYFLOW_DUCKDB_PATH": str(database),
    }
    # dbt has no `python -m` entry point, so call its CLI function directly.
    command = [
        sys.executable, "-c", "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir", str(DBT_DIR),
        "--profiles-dir", str(DBT_DIR),
        "--target-path", str(work_dir / "target"),
        "--log-path", str(work_dir / "logs"),
    ]
    # The command is fixed; the paths are temporary test folders.
    result = subprocess.run(  # noqa: S603
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


def read_marts(database: Path) -> dict[str, list[tuple]]:
    """All rows of every mart, sorted, so two reads compare equal if the data is."""
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return {
            mart: connection.execute(f"select * from {mart} order by all").fetchall()  # noqa: S608
            for mart in MART_KEYS
        }
    finally:
        connection.close()


def count_duplicate_keys(database: Path) -> dict[str, int]:
    """Rows beyond the first for each key, per mart. Zero means the key is unique."""
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return {
            mart: connection.execute(
                f"select count(*) - count(distinct ({', '.join(keys)})) from {mart}"  # noqa: S608
            ).fetchone()[0]
            for mart, keys in MART_KEYS.items()
        }
    finally:
        connection.close()


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory) -> dict[str, list[tuple]]:
    """Marts after the first and the second build of the same fixture."""
    work_dir = tmp_path_factory.mktemp("gold_rebuild")
    fixture_dir = work_dir / "fixture"
    database = work_dir / "gold.duckdb"
    write_silver_fixture(fixture_dir)

    dbt_build(work_dir, fixture_dir, database)
    first = read_marts(database)
    dbt_build(work_dir, fixture_dir, database)
    second = read_marts(database)
    return {
        "first": first,
        "second": second,
        "duplicate_keys": count_duplicate_keys(database),
    }


def test_the_first_build_has_the_expected_rows(rebuilt) -> None:
    rows = {mart: len(table) for mart, table in rebuilt["first"].items()}

    assert rows == FIXTURE_ROWS


def test_building_twice_gives_identical_marts(rebuilt) -> None:
    assert rebuilt["second"] == rebuilt["first"]


def test_building_twice_creates_no_duplicate_keys(rebuilt) -> None:
    assert rebuilt["duplicate_keys"] == dict.fromkeys(MART_KEYS, 0)


def test_a_build_replaces_the_marts_instead_of_adding_to_them(tmp_path) -> None:
    database = tmp_path / "gold.duckdb"
    full_dir, empty_dir = tmp_path / "full", tmp_path / "empty"
    write_silver_fixture(full_dir)
    write_silver_fixture(empty_dir, variant="empty")

    dbt_build(tmp_path, full_dir, database)
    assert {len(t) for t in read_marts(database).values()} != {0}
    dbt_build(tmp_path, empty_dir, database)

    # No row of the first build is left over.
    assert {mart: len(t) for mart, t in read_marts(database).items()} == dict.fromkeys(
        MART_KEYS, 0
    )
