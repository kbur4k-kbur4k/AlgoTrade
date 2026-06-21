import sqlite3

conn = sqlite3.connect('/app/data/paper_trades.db')

# Check if column exists
cursor = conn.execute("PRAGMA table_info(paper_decisions)")
cols = [row[1] for row in cursor.fetchall()]
print("Current columns:", cols)

if "session_id" not in cols:
    conn.execute("ALTER TABLE paper_decisions ADD COLUMN session_id TEXT DEFAULT 'unknown'")
    conn.execute("UPDATE paper_decisions SET session_id = 'unknown' WHERE session_id IS NULL")
    conn.commit()
    print("session_id column added")
else:
    print("session_id column already exists")

cursor = conn.execute("PRAGMA table_info(paper_decisions)")
cols = [row[1] for row in cursor.fetchall()]
print("Final columns:", cols)
conn.close()
