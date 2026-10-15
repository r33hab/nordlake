-- One row per Claude Code session: when it ran, how many prompts, what it cost.

with messages as (

    select * from {{ ref('int_claude_message_costs') }}

),

prompts as (

    select session_id, count(*) as prompts
    from {{ ref('stg_claude_prompts') }}
    group by session_id

)

select
    messages.session_id,
    any_value(messages.project) as project,
    min(messages.sent_at) as started_at,
    max(messages.sent_at) as ended_at,
    date_diff('minute', min(messages.sent_at), max(messages.sent_at)) as duration_minutes,
    coalesce(any_value(prompts.prompts), 0) as prompts,
    count(*) as messages,
    sum(messages.tool_use_blocks) as tool_calls,
    sum(
        messages.input_tokens + messages.cache_write_5m_tokens
        + messages.cache_write_1h_tokens + messages.cache_read_input_tokens
    ) as input_tokens_total,
    sum(messages.output_tokens) as output_tokens,
    round(sum(coalesce(messages.cost_usd, 0)), 4) as cost_usd,
    bool_and(messages.is_priced) as fully_priced
from messages
left join prompts on prompts.session_id = messages.session_id
group by messages.session_id
