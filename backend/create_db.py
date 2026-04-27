import sqlite3

conn = sqlite3.connect('abacus.db')
with open('schema.sql', 'r') as f:
    conn.executescript(f.read())
conn.close()
print('Database created')