-- Spend per day, project and model family, at list price.

select
    cast(sent_at as date) as day,
    project,
    model_family,
    count(*) as messages,
    count(*) filter (where not is_priced) as unpriced_messages,
    sum(input_tokens) as input_tokens,
    sum(cache_write_5m_tokens + cache_write_1h_tokens) as cache_write_tokens,
    sum(cache_read_input_tokens) as cache_read_tokens,
    sum(output_tokens) as output_tokens,
    round(sum(coalesce(cost_usd, 0)), 4) as cost_usd
from {{ ref('int_claude_message_costs') }}
group by 1, 2, 3
