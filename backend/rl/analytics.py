import psycopg2


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "abacus_db",
    "user": "postgres",
    "password": "postgres"
}


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def compute_accuracy_stats():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(
                CASE
                    WHEN remark = 'Correct'
                    THEN 1
                    ELSE 0
                END
            ) as correct
        FROM results
    """)

    row = cur.fetchone()

    total_answers = row[0] or 0
    correct_answers = row[1] or 0

    if total_answers > 0:
        accuracy_percent = round(
            (correct_answers / total_answers) * 100,
            2
        )
    else:
        accuracy_percent = 0

    cur.close()
    conn.close()

    return {
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "accuracy_percent": accuracy_percent
    } 