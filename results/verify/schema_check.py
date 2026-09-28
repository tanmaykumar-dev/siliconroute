import sqlite3

con = sqlite3.connect("data/siliconroute.db")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print("Tables in database:", tables)

for t in tables:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t});").fetchall()]
    print(f"  {t}: {cols}")
