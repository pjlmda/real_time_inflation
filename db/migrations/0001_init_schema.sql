-- Portugal Real-Time Inflation Tracker — initial schema (spec §4)
-- Apply via the Supabase SQL editor. Tables created in FK-dependency order.

-- 4.1 stores
create table stores (
    id smallserial primary key,
    name text not null,
    slug text not null unique,
    base_url text not null,
    robots_checked_at timestamptz,
    country text not null default 'PT'
);

-- 4.2 categories (ECOICOP v2 hierarchy)
create table categories (
    id smallserial primary key,
    ecoicop2_code text not null unique,
    name_pt text not null,
    name_en text not null,
    parent_id smallint references categories (id),
    level smallint not null,
    hicp_weight numeric(7, 4),
    weight_year smallint
);

-- 4.3 products (the fixed basket)
create table products (
    id serial primary key,
    canonical_name text not null,
    brand text,
    is_store_brand boolean not null default false,
    category_id smallint not null references categories (id),
    ean text,
    package_size numeric not null,
    package_unit text not null check (package_unit in ('L', 'kg', 'un', 'g', 'ml')),
    within_cat_weight numeric(7, 4) not null default 1,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (canonical_name, brand)
);

create index products_ean_idx on products (ean) where ean is not null;

-- 4.4 product_listings (store-specific identity)
create table product_listings (
    id serial primary key,
    product_id int not null references products (id),
    store_id smallint not null references stores (id),
    store_sku text,
    ean text,
    url text not null,
    raw_name text,
    match_method text not null check (match_method in ('ean', 'manual', 'fuzzy')),
    is_active boolean not null default true,
    unique (product_id, store_id)
);

-- 4.5 price_snapshots (append-only fact table — never update/delete rows in place)
create table price_snapshots (
    id bigserial primary key,
    listing_id int not null references product_listings (id),
    scrape_date date not null,
    scraped_at timestamptz not null,
    price numeric(8, 2) not null,
    regular_price numeric(8, 2) not null,
    price_per_unit numeric(10, 4) not null,
    unit_basis text not null,
    is_promotion boolean not null default false,
    promotion_label text,
    in_stock boolean not null default true,
    currency text not null default 'EUR',
    raw_payload jsonb not null,
    unique (listing_id, scrape_date)
);

create index price_snapshots_scrape_date_idx on price_snapshots (scrape_date);

-- 4.6 category_observations (DYNAMIC index source)
create table category_observations (
    id bigserial primary key,
    store_id smallint not null references stores (id),
    category_id smallint not null references categories (id),
    scrape_date date not null,
    n_products int not null,
    median_price_per_unit numeric(10, 4),
    mean_price_per_unit numeric(10, 4),
    p25_price_per_unit numeric(10, 4),
    p75_price_per_unit numeric(10, 4),
    raw_payload jsonb,
    unique (store_id, category_id, scrape_date)
);

-- 4.7 inflation_metrics (computed output)
create table inflation_metrics (
    id bigserial primary key,
    as_of_date date not null,
    index_family text not null check (index_family in ('fixed_basket', 'category_avg')),
    period text not null check (period in ('daily', 'weekly', 'monthly', 'yearly')),
    dimension text not null check (dimension in ('overall', 'category', 'subcategory', 'store', 'brand')),
    dimension_value text not null,
    price_basis text not null check (price_basis in ('headline', 'effective')),
    index_value numeric(10, 4) not null,
    inflation_rate numeric(8, 4),
    n_products int,
    coverage numeric(5, 4),
    computed_at timestamptz not null default now(),
    unique (as_of_date, index_family, period, dimension, dimension_value, price_basis)
);

-- 4.8 scrape_runs (observability — drives alerting)
create table scrape_runs (
    id bigserial primary key,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    store_id smallint not null references stores (id),
    mode text not null check (mode in ('basket', 'category')),
    listings_attempted int not null default 0,
    listings_ok int not null default 0,
    listings_failed int not null default 0,
    status text not null default 'success' check (status in ('success', 'partial', 'failed')),
    coverage numeric(5, 4),
    error_summary text,
    alerted boolean not null default false
);

-- 4.9 hicp_weights_cache (Eurostat snapshot, for audit — append-only)
create table hicp_weights_cache (
    id bigserial primary key,
    ecoicop2_code text not null,
    weight_year smallint not null,
    weight numeric(7, 4) not null,
    fetched_at timestamptz not null default now(),
    source_dataset text not null default 'prc_hicp_inw'
);
