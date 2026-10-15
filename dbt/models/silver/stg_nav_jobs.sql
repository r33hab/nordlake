-- One row per ad: the latest version seen in the feed, with the fields pulled out of the JSON.
-- Inactive ads keep only what the feed stub carries (no description, no locations).

with raw as (

    select key, updated_at, ingested_at, payload
    from {{ source('bronze', 'nav_jobs') }}

),

latest as (

    select *
    from raw
    qualify row_number() over (partition by key order by updated_at desc, ingested_at desc) = 1

),

parsed as (

    select
        key as ad_uuid,
        updated_at as modified_at,
        json_extract_string(payload, '$.feed_item._feed_entry.status') as status,
        coalesce(
            json_extract_string(payload, '$.ad.title'),
            json_extract_string(payload, '$.feed_item.title')
        ) as title,
        coalesce(
            json_extract_string(payload, '$.ad.employer.name'),
            json_extract_string(payload, '$.feed_item._feed_entry.businessName')
        ) as employer_name,
        json_extract_string(payload, '$.ad.employer.orgnr') as employer_orgnr,
        coalesce(
            json_extract_string(payload, '$.ad.workLocations[0].municipal'),
            json_extract_string(payload, '$.feed_item._feed_entry.municipal')
        ) as municipality,
        json_extract_string(payload, '$.ad.workLocations[0].county') as county,
        json_extract_string(payload, '$.ad.sector') as sector,
        json_extract_string(payload, '$.ad.engagementtype') as engagement_type,
        json_extract_string(payload, '$.ad.extent') as extent,
        try_cast(json_extract_string(payload, '$.ad.positioncount') as integer) as position_count,
        json_extract_string(payload, '$.ad.jobtitle') as job_title,
        json_extract_string(payload, '$.ad.occupationCategories[0].level1') as occupation_level1,
        json_extract_string(payload, '$.ad.occupationCategories[0].level2') as occupation_level2,
        try_cast(json_extract_string(payload, '$.ad.published') as timestamptz) as published_at,
        try_cast(json_extract_string(payload, '$.ad.expires') as timestamptz) as expires_at,
        json_extract_string(payload, '$.ad.applicationDue') as application_due,
        json_extract_string(payload, '$.ad.source') as ad_source,
        regexp_replace(json_extract_string(payload, '$.ad.description'), '<[^>]+>', ' ', 'g') as description_text,
        json_extract_string(payload, '$.ad') is not null as has_details
    from latest

)

select * from parsed
