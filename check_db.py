import sqlite3

conn = sqlite3.connect('newsroom_demo.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    table_name = table[0]
    try:
        cursor.execute(f'SELECT * FROM {table_name}')
        for row in cursor.fetchall():
            for col in row:
                if isinstance(col, str) and '\\n' in repr(col):
                    print(f'Found newline in {table_name}: {repr(col)[:100]}...')
    except Exception as e:
        pass
