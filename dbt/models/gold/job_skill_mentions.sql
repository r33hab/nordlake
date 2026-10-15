-- How many ads per week mention each skill in the skills seed. One ad can count for many
-- skills; the match runs on title plus description text, lower-cased.

with ads as (

    select
        ad_uuid,
        published_at,
        occupation_level1,
        lower(coalesce(title, '') || ' ' || coalesce(description_text, '')) as text
    from {{ ref('stg_nav_jobs') }}
    where has_details and published_at is not null

),

skills as (

    select * from {{ ref('skills') }}

)

select
    cast(date_trunc('week', ads.published_at) as date) as week,
    ads.occupation_level1,
    skills.skill,
    skills.category,
    count(distinct ads.ad_uuid) as ads
from ads
join skills on regexp_matches(ads.text, skills.pattern)
group by 1, 2, 3, 4
