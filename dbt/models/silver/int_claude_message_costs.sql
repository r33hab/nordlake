-- Price each message with the list prices in the model_prices seed. Messages from a model
-- the seed does not know get a null cost and is_priced = false, so totals can say how much
-- of the bill they cover.

with messages as (

    select * from {{ ref('stg_claude_messages') }}

),

prices as (

    select * from {{ ref('model_prices') }}

)

select
    messages.*,
    prices.model is not null as is_priced,
    (
        messages.input_tokens * prices.input_usd_per_mtok
        + messages.cache_write_5m_tokens * prices.cache_write_5m_usd_per_mtok
        + messages.cache_write_1h_tokens * prices.cache_write_1h_usd_per_mtok
        + messages.cache_read_input_tokens * prices.cache_read_usd_per_mtok
        + messages.output_tokens * prices.output_usd_per_mtok
    ) / 1000000.0 as cost_usd
from messages
left join prices on prices.model = messages.model_family
