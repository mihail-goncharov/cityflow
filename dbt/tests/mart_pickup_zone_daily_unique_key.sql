-- (pickup_date, pickup_location_id) is the key of mart_pickup_zone_daily. A row
-- in the result is a key that appears more than once.
select
    pickup_date,
    pickup_location_id,
    count(*) as row_count
from {{ ref('mart_pickup_zone_daily') }}
group by pickup_date, pickup_location_id
having count(*) > 1
