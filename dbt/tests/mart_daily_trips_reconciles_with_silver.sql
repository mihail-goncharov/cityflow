-- mart_daily_trips must add up to Silver, month by month (docs/gold.md
-- section 5, docs/kpi_dictionary.md section 5). Silver is read straight from the
-- Parquet files (the silver source), not through stg_silver_trips, so a mistake
-- in staging cannot make both sides wrong in the same way. A row in the result
-- is a month whose totals differ, or a month that exists on only one side.
{%- do check_source_months() %}

with silver as (

    select
        source_month,
        count(*) as trip_count,
        sum(fare_amount_cents)::bigint as total_fare_cents,
        sum(total_amount_cents)::bigint as total_charged_cents
    from {{ source('silver', 'yellow_trips') }}
    group by source_month

),

mart as (

    select
        source_month,
        sum(trip_count)::bigint as trip_count,
        sum(total_fare_cents)::bigint as total_fare_cents,
        sum(total_charged_cents)::bigint as total_charged_cents
    from {{ ref('mart_daily_trips') }}
    group by source_month

)

select
    coalesce(silver.source_month, mart.source_month) as source_month,
    silver.trip_count as silver_trips,
    mart.trip_count as mart_trips,
    silver.total_fare_cents as silver_fare_cents,
    mart.total_fare_cents as mart_fare_cents,
    silver.total_charged_cents as silver_charged_cents,
    mart.total_charged_cents as mart_charged_cents
from silver
full join mart
    on mart.source_month = silver.source_month
where silver.source_month is null
    or mart.source_month is null
    or silver.trip_count != mart.trip_count
    or silver.total_fare_cents != mart.total_fare_cents
    or silver.total_charged_cents != mart.total_charged_cents
