-- Eurostat's prc_hicp_inw dataset includes aggregate pseudo-codes (e.g. CP00
-- "all items" = 1000.0 per mille) alongside real COICOP codes. numeric(7,4)
-- (spec §4.2/§4.9) only holds values under 1000, so a fetch against the live
-- API overflows on those aggregate rows. Widen to numeric(8,4) (max
-- 9999.9999) — comfortably covers the observed 0-1000 range with headroom.

alter table categories alter column hicp_weight type numeric(8, 4);
alter table hicp_weights_cache alter column weight type numeric(8, 4);
