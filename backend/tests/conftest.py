"""Endpoint test harness: the real FastAPI app over an in-memory Supabase.

Only the external boundaries are faked — Supabase (DB, auth, storage) and the
Anthropic call. Everything between the HTTP request and the query runs for real.
"""

import itertools
import os
import sys
import uuid
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import practice  # noqa: E402
from app.service.sheet_music_detector import get_sheet_music_detector  # noqa: E402
from app.service.sheet_music_processor import get_sheet_music_processor  # noqa: E402

# Primary keys the fake upserts on; everything else keys on "id".
UPSERT_KEYS = {"section_mastery": ("user_id", "section_id")}
_clock = itertools.count()


class Query:
    """Just enough of the postgrest builder for the calls the app makes."""

    def __init__(self, store, table):
        self.store, self.table = store, table
        self.filters, self.op, self.payload = [], "select", None
        self.order_by, self.limit_n, self.one, self.count_mode = None, None, None, None

    # -- verbs --
    def select(self, *_cols, count=None):
        self.count_mode = count
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def upsert(self, row):
        self.op, self.payload = "upsert", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    # -- filters --
    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        vals = list(vals)
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        assert val == "null"
        self.filters.append(lambda r: r.get(col) is None)
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def single(self):
        self.one = "single"
        return self

    def maybe_single(self):
        self.one = "maybe"
        return self

    # -- run --
    def execute(self):
        rows = self.store.setdefault(self.table, [])
        if self.op == "insert":
            new = self.payload if isinstance(self.payload, list) else [self.payload]
            for row in new:
                row = dict(row)
                row.setdefault("created_at", next(_clock))
                if self.table == "practice_sessions":
                    row.setdefault("started_at", next(_clock))
                    row.setdefault("ended_at", None)
                rows.append(row)
            return SimpleNamespace(data=new, count=None)
        if self.op == "upsert":
            keys = UPSERT_KEYS.get(self.table, ("id",))
            match = [r for r in rows if all(r.get(k) == self.payload.get(k) for k in keys)]
            if match:
                match[0].update(self.payload)
            else:
                rows.append(dict(self.payload))
            return SimpleNamespace(data=[self.payload], count=None)

        hits = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
            return SimpleNamespace(data=hits, count=None)
        if self.op == "delete":
            self.store[self.table] = [r for r in rows if r not in hits]
            return SimpleNamespace(data=hits, count=None)

        if self.order_by:
            col, desc = self.order_by
            hits = sorted(hits, key=lambda r: r.get(col), reverse=desc)
        count = len(hits) if self.count_mode else None
        if self.limit_n is not None:
            hits = hits[: self.limit_n]
        if self.one == "single":
            if len(hits) != 1:
                raise RuntimeError("single() expected exactly one row")
            return SimpleNamespace(data=dict(hits[0]), count=count)
        if self.one == "maybe":
            return SimpleNamespace(data=dict(hits[0]) if hits else None, count=count)
        return SimpleNamespace(data=[dict(r) for r in hits], count=count)


class FakeSupabase:
    def __init__(self):
        self.store = {}
        self.tokens = {}  # token -> user id
        self.files = {}  # storage path -> bytes
        self.auth = SimpleNamespace(get_user=self._get_user)
        self.storage = SimpleNamespace(
            from_=lambda _bucket: SimpleNamespace(download=lambda path: self.files[path])
        )

    def _get_user(self, token):
        if token not in self.tokens:
            raise RuntimeError("invalid JWT")
        return SimpleNamespace(user=SimpleNamespace(id=self.tokens[token]))

    def table(self, name):
        return Query(self.store, name)

    def rows(self, table, **where):
        return [r for r in self.store.get(table, [])
                if all(r.get(k) == v for k, v in where.items())]


def _section(piece_id, start, end):
    return {
        "id": str(uuid.uuid4()),
        "piece_id": piece_id,
        "title": f"mm. {start}-{end}",
        "start_measure": start,
        "end_measure": end,
        "difficulty": 40,
        "notes": "",
        "analysis_data": {
            "risk_measures": [], "techniques": [], "key_challenges": [],
            "tempo_floor": 60, "tempo_target": 100,
        },
    }


def _seed_user(fake, name):
    """One user, one token, one ready piece with two sections and a plan."""
    user_id = str(uuid.uuid4())
    token = f"token-{name}"
    fake.tokens[token] = user_id
    piece_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    sections = [_section(piece_id, 1, 8), _section(piece_id, 9, 16)]
    fake.store.setdefault("profiles", []).append(
        {"id": user_id, "piano_level": "intermediate", "years_experience": 3,
         "onboarding_complete": True})
    fake.store.setdefault("pieces", []).append(
        {"id": piece_id, "user_id": user_id, "title": f"{name}.pdf",
         "file_path": f"{user_id}/{name}.pdf", "status": "ready"})
    fake.store.setdefault("sections", []).extend(sections)
    fake.store.setdefault("practice_plans", []).append(
        {"id": plan_id, "piece_id": piece_id, "version": 1})
    fake.files[f"{user_id}/{name}.pdf"] = b"%PDF-1.4 fake"
    return SimpleNamespace(
        id=user_id, token=token, headers={"Authorization": f"Bearer {token}"},
        piece_id=piece_id, plan_id=plan_id, sections=sections,
    )


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    monkeypatch.setattr(db, "client", lambda: f)
    monkeypatch.setattr(practice, "db", lambda: f)
    auth._verified.clear()
    return f


@pytest.fixture
def llm(monkeypatch):
    """Records Anthropic calls; set `.result` or `.error` to steer them."""
    from app.graph import nodes

    calls = SimpleNamespace(count=0, result=None, error=None)

    def fake_call(*_args, **_kwargs):
        calls.count += 1
        if calls.error:
            raise calls.error
        return calls.result or {}

    monkeypatch.setattr(nodes, "_call", fake_call)
    return calls


@pytest.fixture
def processor(fake):
    """Stands in for SheetMusicProcessor; records background jobs."""
    jobs = []
    service = SimpleNamespace(supabase=fake, process=lambda *a: jobs.append(a), jobs=jobs)
    app.dependency_overrides[get_sheet_music_processor] = lambda: service
    app.dependency_overrides[get_sheet_music_detector] = lambda: SimpleNamespace(
        detect=lambda _bytes: {"sheet_music": True})
    yield service
    app.dependency_overrides.clear()


@pytest.fixture
def alice(fake):
    return _seed_user(fake, "alice")


@pytest.fixture
def bob(fake):
    return _seed_user(fake, "bob")


@pytest.fixture
def client(fake, processor):
    return TestClient(app)
