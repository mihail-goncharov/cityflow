-- (source_month, source_row_id) identifies a trip across all layers
-- (docs/medallion.md section 3), so it must be unique in staging. A row in the
-- result is a duplicated key, which means a trip was read twice. Identical-looking
-- trips are fine: they have different source_row_id values.
select
    source_month,
    source_row_id,
    count(*) as row_count
from {{ ref('stg_silver_trips') }}
group by source_month, source_row_id
having count(*) > 1
