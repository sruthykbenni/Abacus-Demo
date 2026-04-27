import random

class RLThresholdAgent:

    def __init__(self):

        self.thresholds = [0.5, 0.55, 0.6, 0.65, 0.7]

        self.q_table = {
            t: 0.0
            for t in self.thresholds
        }

        self.learning_rate = 0.1

    def select_threshold(self):

        return random.choice(
            self.thresholds
        )

    def update(self, threshold, reward):

        old_value = self.q_table[
            threshold
        ]

        new_value = (
            old_value
            + self.learning_rate
            * (reward - old_value)
        )

        self.q_table[
            threshold
        ] = new_value

    def best_threshold(self):

        return max(
            self.q_table,
            key=self.q_table.get
        )