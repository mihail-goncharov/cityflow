from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "yellow_tripdata_2025-01.parquet"
MANIFEST_FILE = PROJECT_ROOT / "docs" / "source_manifest.json"
CHUNK_SIZE = 1024 * 1024
BASE_URL = "https://d37ci6vzurychx.cloudfront.net"


def sha256_of(path: Path) -> str:
    with open(path, mode="rb") as file:
        hasher = hashlib.sha256()
        while chunk := file.read(CHUNK_SIZE):
            hasher.update(chunk)

        return hasher.hexdigest()


def build_manifest(path: Path, year_month: str) -> dict:
    url = f"{BASE_URL}/trip-data/yellow_tripdata_{year_month}.parquet"
    return {
        "source": "nyc_tlc_yellow",
        "source_month": year_month,
        "url": url,
        "manifest_created_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_of(path)
    }

def main() -> None:
    manifest_data = build_manifest(RAW_FILE, "2025-01")
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, mode="w", encoding="utf-8") as file:
        json.dump(manifest_data, file, indent=2)

if __name__ == "__main__":
    main()