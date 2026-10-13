"""BYOK against the REAL admin-DB wrapper (database.license_db.DictConn / DictRow), backed by sqlite.
Catches wrapper-compat bugs (e.g. row[0] on a DictRow) that pure mocks cannot."""
import sqlite3
import sys
import types

import pytest

if "pyodbc" not in sys.modules:
    try:
        import pyodbc  # noqa: F401
    except Exception:
        sys.modules["pyodbc"] = types.ModuleType("pyodbc")

from database import license_db as LDB            # noqa: E402
from database import byok_migration as MIG        # noqa: E402
import auth.license_service as SVC                # noqa: E402


class RawCursor:
    """Looks like a pyodbc cursor (tuples + .description) on top of sqlite; emulates INFORMATION_SCHEMA.COLUMNS."""
    def __init__(self, c): self.c, self.cur, self._rows, self.description = c, None, None, None
    def execute(self, sql, params=()):
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            t = params[0]
            rows = [(r[1],) for r in self.c.execute(f"PRAGMA table_info({t})").fetchall()]
            self._rows, self.description = rows, [("COLUMN_NAME",)]
            return self
        if sql.strip().upper().startswith("ALTER TABLE") and " ADD " in sql.upper():
            sql = sql.replace(" ADD ", " ADD COLUMN ", 1)
        self.cur = self.c.execute(sql, tuple(params) if params else ())
        self._rows, self.description = None, self.cur.description
        return self
    def fetchone(self):
        if self._rows is not None: return self._rows.pop(0) if self._rows else None
        return self.cur.fetchone()
    def fetchall(self):
        if self._rows is not None:
            r, self._rows = self._rows, []; return r
        return self.cur.fetchall()
    @property
    def rowcount(self): return self.cur.rowcount


class RawConn:
    def __init__(self, c): self.c = c
    def cursor(self): return RawCursor(self.c)
    def commit(self): self.c.commit()
    def close(self): pass


@pytest.fixture()
def db(monkeypatch):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE institutions(id INTEGER PRIMARY KEY AUTOINCREMENT, name, code, client_prefix, db_name, db_server,"
              " db_user, db_password, type, city, status, created_at)")
    c.commit()
    get = lambda: LDB.DictConn(RawConn(c))
    monkeypatch.setattr(MIG, "get_conn", get)
    monkeypatch.setattr(SVC, "get_conn", get)
    monkeypatch.setattr(LDB, "get_conn", get)
    monkeypatch.setattr(SVC, "encrypt_secret", lambda x: "ENC:" + x if x else x)
    return c


def test_migration_adds_columns_with_real_wrapper_and_is_idempotent(db):
    assert MIG.ensure_llm_columns() is True and MIG.READY
    assert MIG.ensure_llm_columns() is True
    cols = {r[1] for r in db.execute("PRAGMA table_info(institutions)")}
    assert {"llm_provider", "llm_model", "llm_api_key", "llm_base_url", "llm_key_status", "llm_key_checked_at"} <= cols


def test_migration_failure_sets_not_ready(monkeypatch):
    monkeypatch.setattr(MIG, "get_conn", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert MIG.ensure_llm_columns() is False and not MIG.READY and "db down" in MIG.LAST_ERROR


def test_create_update_clear_are_atomic_and_key_never_returned(db):
    MIG.ensure_llm_columns()
    d = SVC.create_institution("H", "KON1", "db1", llm_provider="openai", llm_api_key="sk-x", llm_key_status="valid")
    assert d["has_llm_key"] and "llm_api_key" not in d
    assert db.execute("SELECT llm_api_key FROM institutions").fetchone()[0] == "ENC:sk-x"
    SVC.update_institution(d["id"], city="Hyd", llm_api_key="")                 # blank keeps the key
    assert db.execute("SELECT llm_api_key, city FROM institutions").fetchone() == ("ENC:sk-x", "Hyd")
    SVC.update_institution(d["id"], city="Pune", clear_llm_key=True)            # one UPDATE: city + key removal together
    assert db.execute("SELECT city, llm_provider, llm_api_key FROM institutions").fetchone() == ("Pune", None, None)


def test_failed_update_does_not_clear_key(db, monkeypatch):
    MIG.ensure_llm_columns()
    d = SVC.create_institution("H", "KON2", "db2", llm_provider="openai", llm_api_key="sk-y", llm_key_status="valid")
    with pytest.raises(Exception):
        SVC.update_institution(d["id"], clear_llm_key=True, client_prefix=None, name=object())   # bad value => UPDATE fails
    assert db.execute("SELECT llm_api_key FROM institutions").fetchone()[0] == "ENC:sk-y"


def test_failed_update_closes_connection(db, monkeypatch):
    MIG.ensure_llm_columns()
    d = SVC.create_institution("H", "KON3", "db3")
    closed = []
    real = LDB.DictConn
    class Spy(real):
        def close(self): closed.append(1)
    monkeypatch.setattr(SVC, "get_conn", lambda: Spy(RawConn(db)))
    with pytest.raises(Exception):
        SVC.update_institution(d["id"], name=object())
    assert closed == [1]                       # closed exactly once on failure
    SVC.update_institution(d["id"], city="ok")
    assert closed == [1, 1]                    # and exactly once on success
    with pytest.raises(ValueError):
        SVC.update_institution(99999, city="x")
    assert len(closed) == 3
