import sqlite3

con = sqlite3.connect("data/siliconroute.db")
cur = con.cursor()

# Check run columns
run_cols = [r[1] for r in cur.execute("PRAGMA table_info(run);").fetchall()]
if "adapter_vendor" not in run_cols:
    cur.execute("ALTER TABLE run ADD COLUMN adapter_vendor VARCHAR;")
    print("Added run.adapter_vendor")
if "adapter_luid" not in run_cols:
    cur.execute("ALTER TABLE run ADD COLUMN adapter_luid VARCHAR;")
    print("Added run.adapter_luid")
if "identity_suspect" not in run_cols:
    cur.execute("ALTER TABLE run ADD COLUMN identity_suspect BOOLEAN DEFAULT 0 NOT NULL;")
    print("Added run.identity_suspect")

# Check device columns
dev_cols = [r[1] for r in cur.execute("PRAGMA table_info(device);").fetchall()]
if "vendor" not in dev_cols:
    cur.execute("ALTER TABLE device ADD COLUMN vendor VARCHAR;")
    print("Added device.vendor")
if "vendor_id" not in dev_cols:
    cur.execute("ALTER TABLE device ADD COLUMN vendor_id VARCHAR;")
    print("Added device.vendor_id")
if "luid" not in dev_cols:
    cur.execute("ALTER TABLE device ADD COLUMN luid VARCHAR;")
    print("Added device.luid")

con.commit()
con.close()
print("Migration completed successfully.")
