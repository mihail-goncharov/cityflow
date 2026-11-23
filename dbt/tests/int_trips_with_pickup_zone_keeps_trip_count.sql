-- The zone join must neither drop nor multiply trips (docs/gold.md section 5).
-- A row in the result means the trip counts differ.
with staged as (

    select count(*) as trip_count from {{ ref('stg_silver_trips') }}

),

joined as (

    select count(*) as trip_count from {{ ref('int_trips_with_pickup_zone') }}

)

select
    staged.trip_count as staged_trips,
    joined.trip_count as joined_trips
from staged
cross join joined
where staged.trip_count != joined.trip_count
