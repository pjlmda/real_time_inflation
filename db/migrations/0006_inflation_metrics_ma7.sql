-- Phase 3: the plan's §6 methodology calls for the daily headline to be a
-- 7-day moving average ("raw daily is noisy from rounding/promos") — this
-- was never implemented. Nullable, populated only for period='daily' rows
-- (a moving average only makes sense smoothing a daily series); weekly/
-- monthly/yearly rows leave this null.

alter table inflation_metrics add column index_value_ma7 numeric(10, 4);
