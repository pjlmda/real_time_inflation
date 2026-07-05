-- Fuel prices (Part C prototype): Portugal's DGEG national daily average
-- price per fuel type. Deliberately independent of stores/products — a
-- national average isn't a store-specific retail listing (no brand,
-- package size, or store_id applies), so forcing it through the grocery
-- product schema would misrepresent what it is. `scrape_date` here is
-- DGEG's own reported date for that average (there's a reporting lag, so
-- it may lag a day or two behind the day we actually ran the scraper),
-- not the Lisbon "today" convention scraper/db.py uses for groceries.

create table fuel_prices (
    id bigserial primary key,
    fuel_type text not null check (fuel_type in ('gasoline_95', 'diesel', 'lpg_auto')),
    scrape_date date not null,
    price numeric(6, 3) not null,
    unit text not null default 'EUR/L',
    source text not null default 'dgeg_national_average',
    raw_payload jsonb,
    fetched_at timestamptz not null default now(),
    unique (fuel_type, scrape_date)
);

create index fuel_prices_scrape_date_idx on fuel_prices (scrape_date);
