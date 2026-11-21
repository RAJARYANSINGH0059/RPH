"""Alembic migration test: a fresh database upgraded to head must contain every model table."""
import os
import subprocess
import sys
import tempfile

from app.db.session import Base
import app.models  # noqa: F401


def test_alembic_upgrade_head_creates_all_tables():
    d = tempfile.mkdtemp(prefix="ps05x_mig_")
    url = "sqlite:///" + os.path.join(d, "mig.db").replace("\\", "/")
    env = {**os.environ, "DATABASE_URL": url}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    import sqlite3
    con = sqlite3.connect(os.path.join(d, "mig.db"))
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    expected = set(Base.metadata.tables)
    assert expected <= tables, expected - tables
    assert "alembic_version" in tables
    # downgrade works too
    out = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=root, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
