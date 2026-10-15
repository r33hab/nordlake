-- One row per assistant API message. The transcript writes one line per content block and
-- repeats the same usage on each, so lines are collapsed on message id here.

with raw as (

    select key, ingested_at, payload
    from {{ source('bronze', 'claude_transcripts') }}
    where key like 'assistant:%'

),

parsed as (

    select
        json_extract_string(payload, '$.message_id') as message_id,
        try_cast(json_extract_string(payload, '$.ts') as timestamptz) as sent_at,
        json_extract_string(payload, '$.session_id') as session_id,
        json_extract_string(payload, '$.project') as project,
        json_extract_string(payload, '$.model') as model,
        json_extract_string(payload, '$.stop_reason') as stop_reason,
        json_extract_string(payload, '$.git_branch') as git_branch,
        json_extract_string(payload, '$.cc_version') as cc_version,
        json_extract_string(payload, '$.is_sidechain') = 'true' as is_sidechain,
        coalesce(try_cast(json_extract_string(payload, '$.input_tokens') as bigint), 0) as input_tokens,
        coalesce(try_cast(json_extract_string(payload, '$.cache_creation_input_tokens') as bigint), 0) as cache_creation_input_tokens,
        coalesce(try_cast(json_extract_string(payload, '$.cache_read_input_tokens') as bigint), 0) as cache_read_input_tokens,
        coalesce(try_cast(json_extract_string(payload, '$.output_tokens') as bigint), 0) as output_tokens,
        try_cast(json_extract_string(payload, '$.cache_write_5m_tokens') as bigint) as cache_write_5m_raw,
        try_cast(json_extract_string(payload, '$.cache_write_1h_tokens') as bigint) as cache_write_1h_raw,
        coalesce(try_cast(json_extract_string(payload, '$.blocks.tool_use') as integer), 0) as tool_use_blocks,
        coalesce(try_cast(json_extract_string(payload, '$.blocks.text') as integer), 0) as text_blocks,
        coalesce(try_cast(json_extract_string(payload, '$.blocks.thinking') as integer), 0) as thinking_blocks
    from raw

),

deduped as (

    select
        message_id,
        min(sent_at) as sent_at,
        any_value(session_id) as session_id,
        any_value(project) as project,
        any_value(model) as model,
        any_value(stop_reason) as stop_reason,
        any_value(git_branch) as git_branch,
        any_value(cc_version) as cc_version,
        bool_or(is_sidechain) as is_sidechain,
        max(input_tokens) as input_tokens,
        max(cache_creation_input_tokens) as cache_creation_input_tokens,
        max(cache_read_input_tokens) as cache_read_input_tokens,
        max(output_tokens) as output_tokens,
        max(cache_write_5m_raw) as cache_write_5m_raw,
        max(cache_write_1h_raw) as cache_write_1h_raw,
        count(*) as transcript_lines,
        sum(tool_use_blocks) as tool_use_blocks,
        sum(text_blocks) as text_blocks,
        sum(thinking_blocks) as thinking_blocks
    from parsed
    where message_id is not null
      -- Claude Code writes placeholder turns (interruptions, local errors) with this model
      -- name and no usage. They are not API calls, so they do not belong in a cost model.
      and model <> '<synthetic>'
    group by message_id

)

select
    message_id,
    sent_at,
    session_id,
    project,
    model,
    -- Dated snapshot ids (claude-x-y-20250101) price like their family.
    regexp_replace(model, '-[0-9]{8}$', '') as model_family,
    stop_reason,
    git_branch,
    cc_version,
    is_sidechain,
    input_tokens,
    cache_creation_input_tokens,
    cache_read_input_tokens,
    output_tokens,
    -- Older transcripts have no TTL breakdown: treat all cache writes as 5-minute.
    coalesce(cache_write_5m_raw, cache_creation_input_tokens - coalesce(cache_write_1h_raw, 0)) as cache_write_5m_tokens,
    coalesce(cache_write_1h_raw, 0) as cache_write_1h_tokens,
    transcript_lines,
    tool_use_blocks,
    text_blocks,
    thinking_blocks
from deduped
