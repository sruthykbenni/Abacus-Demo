def calculate_reward(
    predicted,
    corrected,
    tolerance=0.01
):

    try:

        p = float(predicted)
        c = float(corrected)

        if abs(p - c) <= tolerance:
            return 1

        return -1

    except:

        if str(predicted).strip() == str(corrected).strip():
            return 1

        return -1