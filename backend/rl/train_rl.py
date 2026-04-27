import psycopg2
from rl_agent import RLThresholdAgent
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "abacus_db",
    "user": "postgres",
    "password": "postgres"
}


def get_data():

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            confidence,
            remark
        FROM results
        WHERE confidence IS NOT NULL
        """
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def train():

    agent = RLThresholdAgent()

    data = get_data()

    for confidence, remark in data:

        if confidence == "Manually corrected":
            continue

        threshold = agent.select_threshold()

        if remark == "Correct":
            reward = 1
        else:
            reward = -1

        agent.update(
            threshold,
            reward
        )

    print(
        "Best threshold learned:",
        agent.best_threshold()
    )


if __name__ == "__main__":
    train()