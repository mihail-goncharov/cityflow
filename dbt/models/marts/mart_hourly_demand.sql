{#-
    One row per pickup date and pickup hour (docs/gold.md section 3). Metrics
    are defined in docs/kpi_dictionary.md section 3.

    An hour with no trips has no row, so avg_fare_cents never divides by 0.
    pickup_date and pickup_hour are Silver's New York local time, so a trip that
    crosses midnight belongs to its pickup hour.

    avg_fare_cents is sum / count rounded to whole cents, half away from zero,
    using integer arithmetic only, so the rounding never sees a float:
        sign(sum) * ((2 * abs(sum) + count) // (2 * count))
    For sum 2001 and count 2 this is (4002 + 2) // 4 = 1001, where 2001 / 2 is
    exactly 1000.5. "//" is integer division in DuckDB.
-#}

with hourly as (

    select
        pickup_date,
        pickup_hour,
        source_month,
        count(*) as trip_count,
        sum(fare_amount_cents)::bigint as total_fare_cents
    from {{ ref('stg_silver_trips') }}
    group by pickup_date, pickup_hour, source_month

)

select
    pickup_date,
    pickup_hour,
    source_month,
    trip_count,
    total_fare_cents,
    (sign(total_fare_cents) * ((2 * abs(total_fare_cents) + trip_count) // (2 * trip_count)))::bigint
        as avg_fare_cents
from hourly
