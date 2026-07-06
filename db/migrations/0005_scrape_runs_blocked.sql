-- Same-day retry (scrape.yml/fuel.yml now run twice daily) needs to know
-- whether a store was explicitly CAPTCHA/block-detected on its first run
-- today, so the retry can skip that store rather than retrying into an
-- active block (spec §7: stop on block detection, don't loop) — `status`
-- alone can't distinguish "failed because blocked" from "failed because
-- every listing errored for some other reason".

alter table scrape_runs add column blocked boolean not null default false;
