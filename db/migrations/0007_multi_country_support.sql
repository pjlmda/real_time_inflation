-- Multi-country support (docs/france-expansion-plan.md §3.1-3.2).
-- Fully additive/backward-compatible: every existing row gets country='PT'
-- via the column default, so this is a no-op for current data and current
-- code paths keep working unmodified until the application code is updated
-- separately to actually use these new columns/table.
--
-- Two real bugs this closes, both silent-corruption risks the moment a
-- second country's data exists:
--   1. inflation_metrics had no country dimension at all. Since COICOP
--      codes are the same international taxonomy in every EU country
--      (dimension='category', dimension_value='01.1.1.3' means "Bread" in
--      both Portugal and France), a second country's category/overall rows
--      would silently collide with and overwrite the first country's.
--   2. categories.hicp_weight is a single column, but HICP weights are
--      genuinely country-specific (France's weight for Bread is a
--      different number from Portugal's, same code). category_weights
--      replaces it with a (ecoicop2_code, country) - scoped table;
--      categories itself stays as the shared, country-agnostic COICOP
--      code/name taxonomy, which it always was.
--
-- categories.hicp_weight/weight_year are deliberately NOT dropped here —
-- application code still reads them. They're dropped in a follow-up
-- migration once every consumer (metrics/compute.py,
-- metrics/category_compute.py, web/api/db.py, weights/eurostat.py) has
-- been switched over to category_weights and verified working.

-- 1. inflation_metrics gains a country dimension, folded into its identity.
alter table inflation_metrics
    add column country text not null default 'PT';

-- Drop the old 6-column unique constraint by discovering its actual
-- Postgres-assigned name rather than guessing it (auto-generated names are
-- derived from the column list and can be truncated/mangled in ways not
-- worth relying on blind).
do $$
declare
    old_constraint_name text;
begin
    select con.conname into old_constraint_name
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    where rel.relname = 'inflation_metrics'
      and con.contype = 'u';

    execute format('alter table inflation_metrics drop constraint %I', old_constraint_name);
end $$;

alter table inflation_metrics
    add constraint inflation_metrics_unique_row
    unique (as_of_date, index_family, period, dimension, dimension_value, price_basis, country);

-- 2. category_weights: per-(code, country) HICP weight, replacing the
-- single hicp_weight column on categories. References categories by code
-- (the shared taxonomy), not by id, since the taxonomy itself never varies
-- by country.
create table category_weights (
    id bigserial primary key,
    ecoicop2_code text not null references categories (ecoicop2_code),
    country text not null,
    hicp_weight numeric(7, 4),
    weight_year smallint,
    unique (ecoicop2_code, country)
);

insert into category_weights (ecoicop2_code, country, hicp_weight, weight_year)
select ecoicop2_code, 'PT', hicp_weight, weight_year
from categories
where hicp_weight is not null;

-- 3. hicp_weights_cache (the Eurostat fetch audit log) needs the same
-- country dimension, so future France/other-country fetches don't read as
-- ambiguous entries alongside Portugal's.
alter table hicp_weights_cache
    add column country text not null default 'PT';
