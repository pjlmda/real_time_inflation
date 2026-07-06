"""Minimal fake double for the `supabase-py` fluent query builder, just
enough surface to unit-test SupabaseWriter without a real Postgres."""
from __future__ import annotations


class FakeQuery:
    def __init__(self, table: "FakeTable", op: str, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters: list[tuple[str, str, object]] = []

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def limit(self, n):
        return self

    def order(self, col, desc=False):
        return self

    def execute(self):
        self.table.calls.append(self)
        if self.op == "select":
            return FakeResponse(self.table.select_results.pop(0) if self.table.select_results else [])
        if self.op in ("insert", "upsert"):
            row = dict(self.payload) if isinstance(self.payload, dict) else self.payload
            if isinstance(row, dict) and "id" not in row:
                row = {**row, "id": self.table.next_id}
                self.table.next_id += 1
            return FakeResponse([row] if isinstance(row, dict) else row)
        if self.op == "update":
            return FakeResponse([self.payload])
        return FakeResponse([])


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[FakeQuery] = []
        self.select_results: list[list[dict]] = []
        self.next_id = 1

    def select(self, *_args, **_kwargs):
        return FakeQuery(self, "select")

    def insert(self, payload):
        return FakeQuery(self, "insert", payload)

    def upsert(self, payload, on_conflict=None):
        return FakeQuery(self, "upsert", payload)

    def update(self, payload):
        return FakeQuery(self, "update", payload)


class FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))
