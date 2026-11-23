{#-
    Silver trips for the months in source_months, with only the columns Gold
    uses, renamed to Gold names (docs/gold.md section 1).

    One row per Silver row: no filtering, no DISTINCT, no quality rules. Gold
    trusts Silver (docs/medallion.md section 7), so every row is an accepted
    trip and is counted.

    Silver is read here rather than through a dbt source, because a source
    cannot call the silver_paths() macro. This model is the only place Gold
    reads Silver.
-#}

with silver as (

    select * from read_parquet({{ silver_paths() }})

)

select
    source_row_id,
    source_month,
    pickup_date,
    pickup_hour,
    PULocationID AS pickup_location_id,
    is_unknown_pickup_zone,
    trip_distance AS trip_distance_miles,
    trip_duration_seconds,
    fare_amount_cents,
    total_amount_cents
from silver
