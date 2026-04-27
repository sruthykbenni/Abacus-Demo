"""
Run this script once to seed initial users into the database.
Usage: python seed_users.py

Passwords are bcrypt-hashed before storing.
"""

import os
import bcrypt
import sqlite3

DB_FILE = os.path.join(os.path.dirname(__file__), "abacus.db")

USERS = [
    {"username": "admin",    "password": "admin123",   "role": "admin",   "name": None},
    {"username": "teacher1", "password": "teacher123", "role": "teacher", "name": None},
    {"username": "rahul",    "password": "student123", "role": "student", "name": "Rahul",
        "contact": "9876543210", "level": "Advanced Level 1", "center": "Kochi Center"},
    {"username": "anjali",   "password": "student123", "role": "student", "name": "Anjali",
        "contact": "9876543211", "level": "Intermediate",     "center": "Kochi Center"},
    {"username": "kiran",    "password": "student123", "role": "student", "name": "Kiran",
        "contact": "9876543212", "level": "Beginner",         "center": "Thrissur Center"},
]


def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed():
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()

    for u in USERS:
        hashed = hash_pw(u["password"])
        try:
            cur.execute(
                "INSERT OR REPLACE INTO users (username, password, role) VALUES (?, ?, ?)",
                (u["username"], hashed, u["role"])
            )
            user_id = cur.lastrowid
            print(f"  User '{u['username']}' ({u['role']}) → id={user_id}")

            if u["role"] == "student" and u.get("name"):
                cur.execute(
                    """
                    INSERT OR IGNORE INTO students (user_id, name, contact, level, center)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, u["name"], u.get("contact"), u.get("level"), u.get("center"))
                )
                print(f"    → Student record created for '{u['name']}'")

        except Exception as e:
            print(f"  ERROR seeding {u['username']}: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    print("\n✅ Seeding complete.")


if __name__ == "__main__":
    print("Seeding database users...\n")
    seed()
