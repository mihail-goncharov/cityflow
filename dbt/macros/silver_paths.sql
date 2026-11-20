{% macro silver_paths(months=none) %}
{#-
    List of Silver Parquet paths, one per month in source_months.

    The layout is the one in docs/medallion.md section 2:
    <CITYFLOW_SILVER_ROOT>/year=<YYYY>/month=<MM>/yellow_tripdata.parquet
    CITYFLOW_SILVER_ROOT has no default: dbt stops if it is not set. A
    malformed or repeated month also stops the build, because a repeated month
    would read the same file twice and double-count its trips. DuckDB itself
    fails if a listed file does not exist.

    The list renders as a DuckDB list literal, so it can be used directly as
    read_parquet({{ silver_paths() }}).
-#}
    {%- set months = months if months is not none else var('source_months') -%}
    {%- if months | length == 0 -%}
        {{ exceptions.raise_compiler_error("source_months must list at least one month") }}
    {%- endif -%}
    {%- set root = env_var('CITYFLOW_SILVER_ROOT').rstrip('/') -%}
    {%- set paths = [] -%}
    {%- for month in months -%}
        {%- if not modules.re.match('^[0-9]{4}-(0[1-9]|1[0-2])$', month | string) -%}
            {{ exceptions.raise_compiler_error("source_months must be YYYY-MM, got '" ~ month ~ "'") }}
        {%- endif -%}
        {%- if month in months[:loop.index0] -%}
            {{ exceptions.raise_compiler_error("source_months lists " ~ month ~ " more than once") }}
        {%- endif -%}
        {%- set year, month_number = (month | string).split('-') -%}
        {%- do paths.append(root ~ '/year=' ~ year ~ '/month=' ~ month_number ~ '/yellow_tripdata.parquet') -%}
    {%- endfor -%}
    {{ return(paths) }}
{% endmacro %}
