# Migrations

Numbered, forward-only SQL files applied manually via the Supabase SQL editor
(`0001_init_schema.sql`, `0002_*.sql`, ...). Each file is idempotent-unsafe by
design (plain `create table`) — apply once per environment, in order, and
never edit a migration that has already been applied anywhere; add a new
numbered file instead.

## Dropping/replacing a constraint by dynamic name lookup

`0007` and `0008` both need to drop an auto-generated constraint name they
can't predict (Postgres derives it from the column list, which can be
truncated/mangled), using a `do $$ ... end $$` block with a `select
con.conname into ...` lookup. A security review of `0008` found this
pattern has real gaps worth closing in `0009` and beyond — both existing
files are already applied, so they're left as-is rather than edited (per
the rule above), but the next migration using this pattern should:

- **Use `select ... into strict`**, not a bare `select ... into`. Plain
  `into` silently takes an arbitrary row on multiple matches and leaves
  the variable `NULL` (which then fails later, confusingly, inside
  `format('%I', ...)`) on zero matches. `strict` raises immediately with a
  clear error in both cases.
- **Filter on the constraint name/columns, not just `contype`**, wherever
  a table could plausibly grow a second constraint of the same type —
  `contype = 'u'` alone matches the first unique constraint Postgres
  happens to return, which is only safe while there's exactly one.
- **Join `pg_namespace` and filter `nspname = 'public'`.** Matching
  `pg_class.relname` alone matches a same-named table in any schema —
  Supabase ships several (`auth`, `storage`, `extensions`, ...).
- **Wrap the whole file in `begin; ... commit;`** when applying via a tool
  that doesn't already give you an implicit transaction per script (the
  Supabase SQL editor does, run as one paste-and-run; `psql -f` without
  `-1` does not). Without it, a mid-file failure — or just the natural gap
  between `drop constraint` and the following `add constraint` — can leave
  the table with no unique constraint at all for a moment, during which an
  `upsert(...on_conflict=...)` from application code can silently
  accumulate duplicate rows instead of erroring.
- **Add `if exists`/`if not exists`** to `drop constraint`/`add column`
  so a partially-applied migration can be safely re-run to completion
  rather than failing on its first already-applied statement.
