{#-
    One row per pickup date and pickup location ID (docs/gold.md section 3).
    Metrics are defined in docs/kpi_dictionary.md section 3.

    Zones 264 (Unknown) and 265 (Outside of NYC) are ordinary rows, marked by
    is_unknown_pickup_zone, so the totals of this mart reconcile with Silver.
    A consumer that leaves them out of a ranking filters on that flag.

    The zone columns are labels of pickup_location_id: one ID has exactly one
    borough, zone name and service zone, so grouping by them does not change the
    grain. The trips come from the zone join, which neither drops nor
    multiplies trips (int_trips_with_pickup_zone).
-#}

select
    pickup_date,
    pickup_location_id,
    source_month,
    pickup_borough,
    pickup_zone,
    pickup_service_zone,
    is_unknown_pickup_zone,
    count(*) as trip_count,
    sum(fare_amount_cents)::bigint as total_fare_cents,
    round(avg(trip_distance_miles), 2) as avg_trip_distance_miles,
    round(avg(trip_duration_seconds), 1) as avg_trip_duration_seconds
from {{ ref('int_trips_with_pickup_zone') }}
group by
    pickup_date,
    pickup_location_id,
    source_month,
    pickup_borough,
    pickup_zone,
    pickup_service_zone,
    is_unknown_pickup_zone
