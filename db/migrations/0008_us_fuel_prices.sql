-- US fuel prices (EIA weekly retail gasoline/diesel data) — extends
-- fuel_prices (migration 0004, originally Portugal/DGEG-only, no country
-- column at all) rather than a separate table, mirroring the same
-- in-place column-add pattern every other multi-country migration in this
-- schema already used (0007: inflation_metrics, hicp_weights_cache,
-- category_weights) rather than forking a per-country table.

-- 1. country, same additive/backward-compatible shape as 0007: every
-- existing (DGEG) row gets country='PT' via the column default, a no-op
-- for current data.
alter table fuel_prices
    add column country text not null default 'PT';

-- 2. region distinguishes a national-average row from a PADD-regional row
-- sharing the same (fuel_type, scrape_date, country). Deliberately NOT
-- nullable with NULL meaning "national": Postgres unique constraints/
-- indexes treat every NULL as distinct from every other NULL, so an
-- upsert's ON CONFLICT target would never match an existing NULL-region
-- row and would silently INSERT a duplicate on every run instead of
-- updating in place — defeating the idempotent-upsert guarantee this
-- project relies on everywhere else. 'NATIONAL' is a concrete,
-- always-equal-to-itself sentinel instead. The default backfills PT's
-- only-ever-national DGEG rows for free; US's own national row uses the
-- same value; PADD codes (confirmed live against EIA's own facet
-- endpoint, not guessed — see fuel/eia.py) go here for the 5 regional
-- rows.
alter table fuel_prices
    add column region text not null default 'NATIONAL';

-- 3. fuel_type's CHECK constraint hardcoded PT's 3 DGEG slugs only. Adds
-- the US regular-gasoline slug. Diesel is intentionally shared across
-- PT/US rows (same commodity concept; country+region already scope the
-- value) — mirrors this project's existing "shared taxonomy, per-country
-- data" shape (categories vs. category_weights). Regular gasoline is NOT
-- folded into PT's gasoline_95: PT's grade is RON (Research Octane
-- Number), the US's is AKI ("Regular Unleaded", ~87) — a different
-- grading system, not a real equivalent, the same "no clean equivalent"
-- reasoning already used to exclude LPG-auto from the US's scope.
do $$
declare
    old_check_name text;
begin
    select con.conname into old_check_name
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    where rel.relname = 'fuel_prices' and con.contype = 'c' and con.conname like '%fuel_type%';

    execute format('alter table fuel_prices drop constraint %I', old_check_name);
end $$;

alter table fuel_prices
    add constraint fuel_prices_fuel_type_check
    check (fuel_type in ('gasoline_95', 'diesel', 'lpg_auto', 'gasoline_regular'));

-- No CHECK constraint on region's actual values: EIA's PADD facet codes
-- are confirmed via a live call during implementation (fuel/eia.py's
-- module docstring), not hardcoded here — a restrictive CHECK against a
-- guess would risk rejecting real EIA data outright if the guess were
-- ever wrong.

-- 4. unit/source defaults were PT/DGEG-specific ('EUR/L',
-- 'dgeg_national_average') and every write path already sets both
-- explicitly per-row (fuel/db.py) — never actually relied on — but
-- leaving them in place now reads as "EUR/L is the normal case", which
-- stops being true once US rows exist. Dropped outright rather than
-- repointed to a different single value, since the "right" default
-- differs per source/country and a table-level default can only pick one.
alter table fuel_prices
    alter column unit drop default;

alter table fuel_prices
    alter column source drop default;

-- 5. Replace the old 2-column unique constraint (fuel_type, scrape_date)
-- — without country+region added, a US PADD-regional row would silently
-- upsert-overwrite the national row (or vice versa) for the same
-- fuel_type/scrape_date. Dynamic name lookup, same pattern as 0007.
do $$
declare
    old_unique_name text;
begin
    select con.conname into old_unique_name
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    where rel.relname = 'fuel_prices' and con.contype = 'u';

    execute format('alter table fuel_prices drop constraint %I', old_unique_name);
end $$;

alter table fuel_prices
    add constraint fuel_prices_unique_row
    unique (fuel_type, scrape_date, country, region);
