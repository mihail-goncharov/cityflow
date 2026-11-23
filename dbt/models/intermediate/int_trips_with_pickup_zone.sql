{#-
    Trips with the attributes of their pickup zone (docs/gold.md section 1).
    Used by mart_pickup_zone_daily.

    One row per trip: the join is on the zone ID, and dim_zone has exactly one
    row per ID, so a trip cannot be multiplied. It is a LEFT join, so a trip is
    never dropped either; a trip whose zone is missing from dim_zone would show
    null zone columns, and the relationships test on stg_silver_trips stops
    the build before that happens.
-#}

select
    trips.source_month,
    trips.source_row_id,
    trips.pickup_date,
    trips.pickup_location_id,
    trips.is_unknown_pickup_zone,
    trips.trip_distance_miles,
    trips.trip_duration_seconds,
    trips.fare_amount_cents,
    trips.total_amount_cents,
    zones.borough as pickup_borough,
    zones.zone as pickup_zone,
    zones.service_zone as pickup_service_zone
from {{ ref('stg_silver_trips') }} as trips
left join {{ ref('dim_zone') }} as zones
    on zones.location_id = trips.pickup_location_id
