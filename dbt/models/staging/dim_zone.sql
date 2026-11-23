{#-
    One row per TLC taxi zone, keyed by location_id (docs/gold.md section 4).

    Built from the committed seed, so it needs no network. IDs 264 (Unknown)
    and 265 (Outside of NYC) keep their TLC labels, and is_unknown_zone marks
    them. Joins to this table use location_id, never the zone name: names are
    not unique.
-#}

select
    LocationID as location_id,
    Borough as borough,
    Zone as zone,
    service_zone,
    LocationID in (264, 265) as is_unknown_zone
from {{ ref('taxi_zone_lookup') }}
