import sqlite3
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "data" / "aibi_phase1.db"
print("DB", p, "exists=", p.exists())
c = sqlite3.connect(p)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("TABLES", tables)
print("USERS", c.execute("SELECT COUNT(*) FROM users").fetchone()[0])
print("WS", c.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0])
print("MEM", c.execute("SELECT COUNT(*) FROM workspace_members").fetchone()[0])
print(
    "OWNER_MEM",
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE role='owner'").fetchone()[0],
)
