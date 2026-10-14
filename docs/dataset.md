# Source profile: NYC TLC Yellow Taxi, 2025-01

## 1. Source

**Dataset:** NYC TLC Yellow Taxi Trip Records, published by the New York City
Taxi and Limousine Commission (TLC).
Catalog page: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

**Scope of this profile:** January 2025 (`source_month = 2025-01`).
The project uses January to March 2025.

**How the data is obtained:**
- One Parquet file per month, downloaded over HTTPS. There is no API.
- URL pattern:
  `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{YYYY-MM}.parquet`
- The storage root does not allow listing files (it returns `AccessDenied`),
  so each URL must be built from the month.
- TLC publishes data monthly, typically with a two-month delay.
- Zone names come from a separate file:
  `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv`

**File identity:** size, SHA-256 and retrieval date are recorded in
[`source_manifest.json`](source_manifest.json). The file was downloaded on
2026-10-05; `manifest_created_at` in the manifest is the time the manifest was built.

**Notes:**
- From 2025, the files include a new column, `cbd_congestion_fee`.
- The data covers trips reported to TLC by yellow taxi vendors. It is not the
  whole of the city's transport demand.


## 2. Volume

| Metric | Value |
|---|---|
| Rows | 3,475,226 |
| Columns | 20 |
| File size on disk | 59,158,238 bytes (about 59 MB) |
| Bytes per row on disk | about 17 |
| Size in memory (Polars) | about 467 MB |
| Earliest pickup | 2024-12-31 20:47:55 |
| Latest pickup | 2025-02-01 00:00:44 |

**Disk versus memory.** The data takes about 8 times more space in memory
than on disk. Parquet stores each column compressed, and in memory every
value is held at full width. Because of this, later pipeline stages should
read files lazily and process one month at a time.

**Period.** The file is named for January 2025, but it contains pickups
from 31 December 2024 to 1 February 2025. The file name shows the month
TLC assigned the records to, not the date of every trip. Rows outside
January are counted in section 5.

**Estimate for the project (January to March 2025).** Assuming the other
two months are similar in size: about 10 million rows, about 180 MB on
disk and about 1.4 GB in memory. This is an estimate and will be replaced
with measured values once February and March are downloaded.


## 3. Entities

The file is a fact table: one row is one trip. Other entities appear
only as codes, and their descriptions are stored outside the file.

| Entity | Where it appears in the trip file | What it is | Descriptions come from |
|---|---|---|---|
| Trip | the whole row (all 20 columns) | One taxi ride: times, distance, amounts | the Parquet file |
| Taxi zone | `PULocationID`, `DOLocationID` | Zone where the meter was engaged or disengaged | `taxi_zone_lookup.csv` (265 rows: borough, zone, service zone) |
| Vendor | `VendorID` | TPEP provider that sent the record | data dictionary (4 codes) |
| Rate code | `RatecodeID` | Final rate code in effect at the end of the trip | data dictionary (7 codes) |
| Payment type | `payment_type` | How the passenger paid | data dictionary (7 codes) |
| Date | derived from `tpep_pickup_datetime`, `tpep_dropoff_datetime` | Calendar day of the trip | generated |

**Two columns, one entity.** Every trip points to the taxi zone list
twice: once for pickup and once for dropoff.

**Not in the data.** There is no ID for the vehicle, the driver or the
passenger. `passenger_count` is a number that describes the trip. Analysis
by individual car, driver or customer is not possible.

**Not an entity.** `store_and_fwd_flag` is a yes/no attribute of the trip.

**No trip ID.** The file has no column that identifies a trip, and
identical rows are possible. A technical ID (`source_row_id`) will be
added in the Silver layer.


## 4. Columns

Meanings are taken from the TLC data dictionary for Yellow Taxi Trip
Records (version of March 18, 2025). Types are as read by Polars.

| Column | Type | Meaning | Nulls   |
|---|---|---|---------|
| `VendorID` | Int32 | Code of the TPEP provider that sent the record. 1 = Creative Mobile Technologies, LLC; 2 = Curb Mobility, LLC; 6 = Myle Technologies Inc; 7 = Helix | 0       |
| `tpep_pickup_datetime` | Datetime (μs, no time zone) | Date and time when the meter was engaged | 0       |
| `tpep_dropoff_datetime` | Datetime (μs, no time zone) | Date and time when the meter was disengaged | 0       |
| `passenger_count` | Int64 | Number of passengers in the vehicle | 540,149 |
| `trip_distance` | Float64 | Trip distance in miles reported by the taximeter | 0       |
| `RatecodeID` | Int64 | Final rate code in effect at the end of the trip. 1 = Standard rate; 2 = JFK; 3 = Newark; 4 = Nassau or Westchester; 5 = Negotiated fare; 6 = Group ride; 99 = Null/unknown | 540,149 |
| `store_and_fwd_flag` | String | Whether the record was held in vehicle memory before being sent to the vendor because there was no connection. Y = yes; N = no | 540,149 |
| `PULocationID` | Int32 | TLC taxi zone where the meter was engaged | 0       |
| `DOLocationID` | Int32 | TLC taxi zone where the meter was disengaged | 0       |
| `payment_type` | Int64 | How the passenger paid. 0 = Flex Fare trip; 1 = Credit card; 2 = Cash; 3 = No charge; 4 = Dispute; 5 = Unknown; 6 = Voided trip | 0       |
| `fare_amount` | Float64 | Time-and-distance fare calculated by the meter | 0       |
| `extra` | Float64 | Miscellaneous extras and surcharges | 0       |
| `mta_tax` | Float64 | Tax triggered automatically by the metered rate in use | 0       |
| `tip_amount` | Float64 | Tip amount. Filled automatically for credit card tips; cash tips are not included | 0       |
| `tolls_amount` | Float64 | Total of all tolls paid in the trip | 0       |
| `improvement_surcharge` | Float64 | Improvement surcharge charged at the flag drop | 0       |
| `total_amount` | Float64 | Total amount charged to passengers. Does not include cash tips | 0       |
| `congestion_surcharge` | Float64 | Amount collected for the NYS congestion surcharge | 540,149 |
| `Airport_fee` | Float64 | Fee for pickups at LaGuardia and John F. Kennedy airports only | 540,149 |
| `cbd_congestion_fee` | Float64 | Per-trip charge for the MTA Congestion Relief Zone, starting Jan. 5, 2025 | 0       |

### Notes

- **Name mismatch.** The dictionary lists `airport_fee`, and the file has
  `Airport_fee` with a capital A. Code must use the name from the file.
- **Money is stored as Float64.** Floating-point values are approximate, so
  amounts will be converted to cents or DECIMAL in the Silver layer.
- **No time zone.** The two timestamp columns carry no time zone, and the
  dictionary does not state one. Open question: confirm that the values
  are New York local time.
- **Cash tips are missing by design.** `tip_amount` and `total_amount`
  exclude cash tips, so tip analysis is valid for card payments only.
- **`RatecodeID = 99` and `payment_type = 5` mean "unknown".** They are
  valid codes, not errors, and are separate from null.
- **Five columns have the same null count (540,149, about 15.5% of rows):**
  `passenger_count`, `RatecodeID`, `store_and_fwd_flag`,
  `congestion_surcharge` and `Airport_fee`. They are the same rows: all of
  them have `payment_type = 0` (Flex Fare trip).

### Taxi zone lookup (`taxi_zone_lookup.csv`)

- 265 rows, `LocationID` from 1 to 265, with columns `Borough`, `Zone`
  and `service_zone`.
- Two IDs are not real zones: 264 (`Borough` = "Unknown") and
  265 (`Zone` = "Outside of NYC").
- Zone names are not unique: IDs 56 and 57 are both "Corona", and IDs 103,
  104 and 105 share one name. Joins must use `LocationID`, never the name.


## 5. Available period

The TLC catalog page publishes Yellow Taxi data as one Parquet file per month.
When checked on 2026-10-10, it listed monthly files from at least 2015 up to
August 2026. New months appear with a delay of about two months.

The project uses January to March 2025; this profile covers January 2025.


## 6. Fields useful for analytics

| Field | Used for |
|---|---|
| `tpep_pickup_datetime`, `tpep_dropoff_datetime` | trips per day and per hour, trip duration |
| `PULocationID`, `DOLocationID` | top pickup and dropoff zones, routes (joined with the zone lookup) |
| `trip_distance` | average distance, speed checks |
| `total_amount` | total charged to the passenger, including taxes and fees (not revenue) |
| `fare_amount` | metered fare without surcharges and taxes |
| `tip_amount` | tips, valid for card payments only (cash tips are not recorded) |
| `payment_type` | comparison of payment methods; identifies Flex Fare trips |
| `RatecodeID` | separating airport and negotiated fares from standard trips |
| `VendorID` | data quality by provider |

Less useful for analytics: `store_and_fwd_flag` (a technical flag about data
transfer) and the fixed charges `mta_tax` and `improvement_surcharge`.


## 7. Potential business metrics

- Trips per day and per hour, busiest hour
- Total fare amount and average fare per trip (`fare_amount`; not revenue)
- Average trip distance and average trip duration
- Top pickup and dropoff zones, popular routes
- Payment method share and tip rate (card payments only)
- Share of airport trips (JFK, LaGuardia, Newark)


## 8. Known limitations

- No vehicle, driver, passenger or trip ID: analysis per car, driver or
  customer is not possible.
- Cash tips are not recorded, so tip analysis covers card payments only.
- Timestamps have no time zone (assumed to be New York local time).
- Money is stored as Float64, which is approximate.
- 15.5% of rows (Flex Fare trips) have no passenger count, rate code or
  surcharge data.
- About 6.5% of rows have quality problems and are excluded from the
  metrics; see `data_quality_findings.md`.


## 9. Data quality

Data quality problems, with counts, examples and planned handling, are
described in [`data_quality_findings.md`](data_quality_findings.md).
