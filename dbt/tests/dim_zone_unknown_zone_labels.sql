-- Zones 264 and 265 must exist with their documented TLC labels
-- (docs/gold.md section 4). A row in the result is a missing zone or a changed
-- label, for example after an update of the seed file.
with expected as (

    select * from (values
        (264, 'Unknown', 'N/A', 'N/A'),
        (265, 'N/A', 'Outside of NYC', 'N/A')
    ) as t (location_id, borough, zone, service_zone)

)

select
    expected.location_id
from expected
left join {{ ref('dim_zone') }} as dim_zone
    on dim_zone.location_id = expected.location_id
where dim_zone.location_id is null
    or dim_zone.borough != expected.borough
    or dim_zone.zone != expected.zone
    or dim_zone.service_zone != expected.service_zone
    or not dim_zone.is_unknown_zone
