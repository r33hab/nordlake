-- Ads published per day, sector and occupation group. Only ads with full details carry
-- a publish date, so inactive stubs are not counted here.

select
    cast(published_at as date) as day,
    sector,
    occupation_level1,
    count(*) as ads,
    sum(coalesce(position_count, 1)) as positions,
    count(distinct employer_orgnr) as employers
from {{ ref('stg_nav_jobs') }}
where has_details and published_at is not null
group by 1, 2, 3
