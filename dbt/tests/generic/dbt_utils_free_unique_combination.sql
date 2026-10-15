{#- A unique-combination test without pulling in dbt_utils for one macro. -#}
{% test dbt_utils_free_unique_combination(model, columns) %}

select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1

{% endtest %}
