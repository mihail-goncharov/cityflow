{% macro check_source_months(months=none) %}
{#-
    Stop the build if source_months is not a valid list of months.

    The Silver path list itself is built in models/staging/_sources.yml, which
    cannot call macros, so the checks live here. Everything that reads the
    silver source calls this macro first: stg_silver_trips and the
    reconciliation tests (which can be run on their own). It fails on:
    - an empty list;
    - a month that is not YYYY-MM, which would build a wrong path;
    - a month listed twice, which would read the same file twice and
      double-count its trips.
-#}
    {%- set months = months if months is not none else var('source_months') -%}
    {%- if months | length == 0 -%}
        {{ exceptions.raise_compiler_error("source_months must list at least one month") }}
    {%- endif -%}
    {%- for month in months -%}
        {%- if not modules.re.match('^[0-9]{4}-(0[1-9]|1[0-2])$', month | string) -%}
            {{ exceptions.raise_compiler_error("source_months must be YYYY-MM, got '" ~ month ~ "'") }}
        {%- endif -%}
        {%- if month in months[:loop.index0] -%}
            {{ exceptions.raise_compiler_error("source_months lists " ~ month ~ " more than once") }}
        {%- endif -%}
    {%- endfor -%}
{% endmacro %}
