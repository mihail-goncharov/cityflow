{#-
    One row per pickup date (docs/gold.md section 3). Metrics are defined in
    docs/kpi_dictionary.md section 3.

    Trips are counted exactly as they are in Silver: no DISTINCT, so
    identical-looking trips are all counted. A trip that crosses midnight
    belongs to its pickup date, which Silver already computed.

    sum() of BIGINT returns HUGEINT in DuckDB, so the sums are cast back to
    BIGINT, the type the KPI dictionary promises.
-#}

select
    pickup_date,
    source_month,
    count(*) as trip_count,
    sum(fare_amount_cents)::bigint as total_fare_cents,
    sum(total_amount_cents)::bigint as total_charged_cents,
    round(avg(trip_distance_miles), 2) as avg_trip_distance_miles,
    round(avg(trip_duration_seconds), 1) as avg_trip_duration_seconds
from {{ ref('stg_silver_trips') }}
group by pickup_date, source_month
