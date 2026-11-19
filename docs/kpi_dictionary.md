# KPI dictionary

**Status:** draft for AB#5. Every metric in the Gold marts
([`gold.md`](gold.md), section 3) is defined here. A metric that is not in this
document must not appear in a mart.

All metrics are computed from Silver ([`medallion.md`](medallion.md), section
4), so every counted trip has already passed the quality rules.


## 1. Common rules

- **Grain.** Every metric is computed per row of its mart: per `pickup_date`,
  per `pickup_date` + `pickup_hour`, or per `pickup_date` +
  `pickup_location_id`.
- **Denominator.** Every average divides by `trip_count` of the same mart row.
  A mart row exists only if it has at least one trip, so the denominator is
  never 0.
- **Nulls.** All input columns used below are not null in Silver
  (`medallion.md` section 4.4), so no metric has to skip or replace nulls. The
  staging model tests this with `not_null`, so a broken assumption fails the
  build instead of silently changing an average.
- **Money is exact.** Money is summed as integer cents (`BIGINT`), so totals
  have no floating-point error and reconcile exactly with Silver.
- **Rounding of money averages:** to whole cents, half away from zero, from the
  exact value `sum / count` (not from a float). The result is `BIGINT` cents.
- **Rounding of other averages:** distance to 2 decimals (miles), duration to 1
  decimal (seconds), `DOUBLE`. Ties are not meaningful for these measures.
- **Units.** Money is in US cents (divide by 100 for dollars, which is a
  display decision for the dashboard). Distance is in miles as reported by the
  taximeter. Time is in seconds.
- **Unknown zones** (IDs 264 and 265) are included in every metric. They are
  excluded only where a consumer filters on `is_unknown_pickup_zone`
  explicitly.


## 2. What the money columns mean

| Term | Silver column | Meaning |
|---|---|---|
| **Metered fare** | `fare_amount_cents` | The time-and-distance fare calculated by the meter. Excludes surcharges, taxes, tolls and tips. |
| **Total charged** | `total_amount_cents` | Everything charged to the passenger: fare, surcharges, taxes, tolls and card tips. |

- Neither is **net revenue or profit**. They are amounts charged to passengers,
  before driver pay, fees and costs, which the data does not contain. They must
  not be labelled as revenue in the dashboard.
- **Cash tips are not recorded** by TLC (`dataset.md`). `total_amount`
  includes card tips only, so total charged is lower than what passengers
  really paid on cash trips.
- In accepted trips `fare_amount` is above 0 and at most 1,000 dollars. Other
  money columns, including `total_amount`, can be negative (refunds and
  adjustments, `medallion.md` section 4.1), so a total charged can include
  negative trips.


## 3. Metrics

### `trip_count`

| | |
|---|---|
| Meaning | Number of accepted trips at the grain. |
| SQL | `count(*)` |
| Input | Silver rows (one row = one trip; duplicates are separate trips) |
| Type, unit | `BIGINT`, trips |
| Used in | all three marts |
| Limitations | Counts accepted trips only; rejected trips are in Quarantine. |

### `total_fare_cents`

| | |
|---|---|
| Meaning | Sum of the metered fare. |
| SQL | `sum(fare_amount_cents)` |
| Input | `fare_amount_cents` |
| Type, unit | `BIGINT`, US cents |
| Used in | all three marts |
| Limitations | Not revenue (section 2). |

### `total_charged_cents`

| | |
|---|---|
| Meaning | Sum of the total amount charged to passengers. |
| SQL | `sum(total_amount_cents)` |
| Input | `total_amount_cents` |
| Type, unit | `BIGINT`, US cents |
| Used in | `mart_daily_trips` |
| Limitations | Not revenue; excludes cash tips; can include negative adjustments (section 2). |

### `avg_fare_cents`

| | |
|---|---|
| Meaning | Average metered fare per trip. |
| SQL | `sum(fare_amount_cents) / count(*)`, rounded to whole cents, half away from zero |
| Input | `fare_amount_cents` |
| Type, unit | `BIGINT`, US cents |
| Denominator | `trip_count` of the same row |
| Used in | `mart_hourly_demand` |
| Limitations | Rounded, so `avg_fare_cents * trip_count` is close to but not always equal to `total_fare_cents`. Reconcile with the total, not the average. |

### `avg_trip_distance_miles`

| | |
|---|---|
| Meaning | Average trip distance. |
| SQL | `round(avg(trip_distance), 2)` |
| Input | `trip_distance` |
| Type, unit | `DOUBLE`, miles |
| Denominator | `trip_count` of the same row |
| Used in | `mart_daily_trips`, `mart_pickup_zone_daily` |
| Limitations | Distance is the taximeter's value; accepted trips have 0 < distance <= 200. |

### `avg_trip_duration_seconds`

| | |
|---|---|
| Meaning | Average time from pickup to dropoff. |
| SQL | `round(avg(trip_duration_seconds), 1)` |
| Input | `trip_duration_seconds` |
| Type, unit | `DOUBLE`, seconds |
| Denominator | `trip_count` of the same row |
| Used in | `mart_daily_trips`, `mart_pickup_zone_daily` |
| Limitations | Timestamps have no time zone, so a duration on a daylight-saving changeover night can be off by one hour (`medallion.md` section 5). Accepted trips last 1 to 18,000 seconds. |


## 4. Zone attributes (not metrics)

`mart_pickup_zone_daily` also carries the pickup zone's descriptive columns
from `dim_zone`. They are labels, not measures, and are never aggregated.

| Column | Source | Notes |
|---|---|---|
| `pickup_borough` | `Borough` | `Unknown` for ID 264 |
| `pickup_zone` | `Zone` | `Outside of NYC` for ID 265; names are not unique |
| `pickup_service_zone` | `service_zone` | |
| `is_unknown_pickup_zone` | ID is 264 or 265 | Filter on this to exclude unknown zones from a ranking |


## 5. Reconciliation

For each month in the build, these must hold (tested, `gold.md` section 5):

- `sum(trip_count)` of each mart = number of Silver rows.
- `sum(total_fare_cents)` of each mart = `sum(fare_amount_cents)` of Silver.
- `sum(total_charged_cents)` of `mart_daily_trips` =
  `sum(total_amount_cents)` of Silver.

Averages are not reconciled, because rounding makes them inexact by design.
