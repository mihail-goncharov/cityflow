-- (pickup_date, pickup_hour) is the key of mart_hourly_demand. A row in the
-- result is a key that appears more than once.
select
    pickup_date,
    pickup_hour,
    count(*) as row_count
from {{ ref('mart_hourly_demand') }}
group by pickup_date, pickup_hour
having count(*) > 1
