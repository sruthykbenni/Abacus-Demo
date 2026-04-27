from rl.analytics import compute_accuracy_stats
from rl.trend_logger import log_accuracy

def run_dashboard():

    stats = compute_accuracy_stats()

    print("\n===== SYSTEM PERFORMANCE =====")

    print(
        "Total answers:",
        stats["total_answers"]
    )

    print(
        "Correct answers:",
        stats["correct_answers"]
    )

    print(
        "Accuracy:",
        stats["accuracy_percent"],
        "%"
    )

    log_accuracy(
        stats["accuracy_percent"]
    )

    print("\nAccuracy logged successfully.")


if __name__ == "__main__":

    run_dashboard()