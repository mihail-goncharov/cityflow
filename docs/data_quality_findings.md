# Data quality findings

Dataset: NYC TLC Yellow Taxi, January 2025 (`data/raw/yellow_tripdata_2025-01.parquet`).
3,475,226 rows, 20 columns. All numbers come from `src/cityflow/profile_data.py`.
The source file is never modified; this document only describes the problems.

Handling: **retain** = keep as is · **flag** = keep, but exclude from affected metrics ·
**reject** = exclude from metrics.

## Summary

| # | Problem | Rows | % | Handling |
|---|---|---:|---:|---|
| 1 | Missing passenger and trip fields | 540,149 | 15.54% | flag |
| 2 | Zero or negative fare | 145,516 | 4.19% | reject |
| 3 | Zero distance | 90,893 | 2.62% | reject |
| 4 | Unknown location (ID 264/265) | 28,357 | 0.82% | retain |
| 5 | Zero duration with distance | 1,235 | 0.04% | reject |
| 6 | Trip longer than 5 hours | 1,233 | 0.04% | reject |
| 7 | Dropoff before pickup | 124 | <0.01% | reject |
| 8 | Distance over 200 miles | 122 | <0.01% | reject |
| 9 | Pickup outside January 2025 | 22 | <0.01% | reject |
| 10 | Fare over $1,000 | 3 | <0.01% | reject |

A row can have several problems. After excluding rows with problems 2, 3 and 5–10,
**3,251,195 valid trips** remain (224,031 rows, 6.45%, excluded).

## 1. Missing passenger and trip fields

- **What:** `passenger_count`, `RatecodeID`, `store_and_fwd_flag`, `congestion_surcharge`
  and `Airport_fee` are null, always together.
- **Rows:** 540,149 (15.54%). All of them have `payment_type = 0` (Flex Fare trip).
- **Example:** `passenger_count = null, RatecodeID = null, VendorID = 2, payment_type = 0`.
- **Possible cause:** Flex Fare trips are reported without these fields.
- **Handling:** flag. The trips are real, so they stay in trip, fare and location
  metrics, but not in passenger analysis.

## 2. Zero or negative fare

- **Rows:** 145,516 (4.19%). Minimum fare: -$900.
- **Example:** `fare_amount = -138.8, total_amount = -159.11, payment_type = 4 (Dispute)`.
- **Possible cause:** refunds, disputes and cancelled trips. All negative fares come
  from one vendor (VendorID 2).
- **Handling:** reject from fare metrics.

## 3. Zero distance

- **Rows:** 90,893 (2.62%).
- **Example:** `trip_distance = 0.0, fare_amount = 48.5, 09:39 → 10:20`.
- **Possible cause:** GPS or odometer not recording, or a fixed negotiated fare.
- **Handling:** reject.

## 4. Missing or unknown location

- **What:** no location ID is null, but TLC uses special IDs for unknown places:
  264 = Unknown, 265 = Outside of NYC (`taxi_zone_lookup.csv`).
- **Rows:** 0 null; 28,357 (0.82%) use 264 or 265.
- **Possible cause:** location could not be matched to a zone, or the trip ended outside NYC.
- **Handling:** retain. They do not appear in the top-10 zone lists.

## 5. Zero duration with distance

- **Rows:** 1,235 (0.04%), mostly VendorID 7.
- **Example:** `08:11:49 → 08:11:49, trip_distance = 3.05, fare_amount = 13.5`.
- **Possible cause:** the device wrote the same time into pickup and dropoff.
- **Handling:** reject.

## 6. Trip longer than 5 hours

- **Rows:** 1,233 (0.04%). Most last around 22–24 hours.
- **Example:** `2025-01-22 19:39 → 2025-01-23 19:09, trip_distance = 1.43, fare_amount = 10.7`.
- **Possible cause:** the meter was not stopped at the end of the trip.
- **Handling:** reject, because it distorts the average duration.

## 7. Dropoff before pickup

- **Rows:** 124 (<0.01%), mostly VendorID 6.
- **Example:** `23:01:59 → 23:01:10, trip_distance = 15.94`.
- **Possible cause:** device clock error.
- **Handling:** reject.

## 8. Distance over 200 miles

- **Rows:** 122 (<0.01%).
- **Example:** `72,742.93 miles in 19 minutes`.
- **Possible cause:** broken distance value. Physically impossible.
- **Handling:** reject.

## 9. Pickup outside January 2025

- **Rows:** 22 (<0.01%). Range: 2024-12-31 20:47 to 2025-02-01 00:00.
- **Possible cause:** trips reported in the wrong month's file.
- **Handling:** reject from January metrics.

## 10. Fare over $1,000

- **Rows:** 3 (<0.01%).
- **Example:** 1.6 miles in 5 minutes for $863,372.12, `payment_type = 4 (Dispute)`.
  The other two are long trips (189 and 255 miles) and may be real.
- **Possible cause:** data-entry error for the first row.
- **Handling:** reject all three from fare metrics at this stage.

## Assumptions

- The limits of 200 miles, 5 hours and $1,000 are my own choices, not TLC rules.
- `fare_amount` is only the meter price. It is not revenue: tips, taxes, tolls and
  surcharges are in `total_amount`.

## Next stage

Apply these rules in the Silver layer (#4) and keep rejected rows in a separate table
instead of deleting them.
