# Migrations

Numbered, forward-only SQL files applied manually via the Supabase SQL editor
(`0001_init_schema.sql`, `0002_*.sql`, ...). Each file is idempotent-unsafe by
design (plain `create table`) — apply once per environment, in order, and
never edit a migration that has already been applied anywhere; add a new
numbered file instead.
