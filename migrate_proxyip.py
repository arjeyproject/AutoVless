import sqlite3
import sys

db_path = '/opt/autovless/data/autovless.db'
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE panels ADD COLUMN proxyip TEXT DEFAULT NULL;")
    conn.commit()
    print("✓ Migration successful: proxyip column added")
except sqlite3.OperationalError as e:
    if 'duplicate column name' in str(e):
        print("✓ Column already exists")
    else:
        print(f"✗ Error: {e}")
        sys.exit(1)
finally:
    conn.close()
