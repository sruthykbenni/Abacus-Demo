import csv
from datetime import datetime
from pathlib import Path


TREND_FILE = Path("accuracy_trend.csv")


def log_accuracy(value):

    file_exists = TREND_FILE.exists()

    with open(
        TREND_FILE,
        "a",
        newline=""
    ) as f:

        writer = csv.writer(f)

        if not file_exists:

            writer.writerow(
                [
                    "timestamp",
                    "accuracy"
                ]
            )

        writer.writerow(
            [
                datetime.now(),
                value
            ]
        )