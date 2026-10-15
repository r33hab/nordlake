-- One row per prompt a person typed. Tool results, meta turns and sidechains are user-role
-- lines too, but nobody typed them, so they are excluded.

with raw as (

    select key, ingested_at, payload
    from {{ source('bronze', 'claude_transcripts') }}
    where key like 'user:%'
    qualify row_number() over (partition by key order by ingested_at desc) = 1

)

select
    json_extract_string(payload, '$.uuid') as prompt_uuid,
    try_cast(json_extract_string(payload, '$.ts') as timestamptz) as sent_at,
    json_extract_string(payload, '$.session_id') as session_id,
    json_extract_string(payload, '$.project') as project,
    json_extract_string(payload, '$.git_branch') as git_branch
from raw
where json_extract_string(payload, '$.is_tool_result') = 'false'
  and json_extract_string(payload, '$.is_meta') = 'false'
  and json_extract_string(payload, '$.is_sidechain') = 'false'
