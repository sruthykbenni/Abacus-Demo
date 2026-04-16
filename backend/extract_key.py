import re

import fitz


QUESTION_NUMBER_LIMIT = 200
ROW_TOLERANCE = 2.0
ROW_CLUSTER_TOLERANCE = 8.0
NUMERIC_TOKEN_RE = re.compile(r"-?(?:\d+(?:[.,]\d+)?|\.\d+)")


def normalize_numeric_token(token):
    token = str(token).strip().replace(",", ".")
    if token.startswith("."):
        token = f"0{token}"
    elif token.startswith("-."):
        token = token.replace("-.", "-0.", 1)
    return token


def parse_question_numbers(values):
    if not values:
        return None

    question_nums = []
    for value in values:
        if "." in value:
            return None
        try:
            question_nums.append(int(value))
        except ValueError:
            return None

    return question_nums


def is_arithmetic_progression(nums):
    if len(nums) < 3:
        return False

    step = nums[1] - nums[0]
    if step <= 0:
        return False

    return all(nums[i + 1] - nums[i] == step for i in range(len(nums) - 1))


def looks_like_question_blocks(blocks):
    if not blocks:
        return False

    flat = [num for block in blocks for num in block["question_nums"]]
    if not flat or min(flat) != 1:
        return False

    unique = sorted(set(flat))
    return len(flat) == len(unique) and unique == list(range(1, unique[-1] + 1))


def extract_numeric_blocks(page):
    numeric_blocks = []
    for block in page.get_text("blocks"):
        values = [
            normalize_numeric_token(token)
            for token in NUMERIC_TOKEN_RE.findall(block[4])
        ]
        if not values:
            continue

        numeric_blocks.append(
            {
                "x0": block[0],
                "y0": block[1],
                "values": values,
                "question_nums": parse_question_numbers(values),
            }
        )

    return numeric_blocks


def is_question_candidate(question_nums):
    if not question_nums or max(question_nums) > QUESTION_NUMBER_LIMIT:
        return False

    if len(question_nums) == 1:
        return True

    step = question_nums[1] - question_nums[0]
    if step <= 0:
        return False

    return all(
        question_nums[i + 1] - question_nums[i] == step
        for i in range(len(question_nums) - 1)
    )


def contiguous_question_coverage(blocks):
    if not blocks:
        return 0

    flat = [num for block in blocks for num in block["question_nums"]]
    if not flat or min(flat) != 1 or len(flat) != len(set(flat)):
        return 0

    unique = sorted(set(flat))
    coverage = 0
    for expected in range(1, unique[-1] + 1):
        if expected not in unique:
            break
        coverage = expected

    return coverage


def dedupe_question_blocks(blocks):
    best_by_num = {}
    for block in blocks:
        for num in block["question_nums"]:
            existing = best_by_num.get(num)
            if existing is None:
                best_by_num[num] = block
                continue

            # Prefer blocks that sit farther left, then farther down.
            current_key = (block["x0"], -block["y0"])
            existing_key = (existing["x0"], -existing["y0"])
            if current_key < existing_key:
                best_by_num[num] = block

    deduped = []
    seen = set()
    for num in sorted(best_by_num):
        block = best_by_num[num]
        block_id = id(block)
        if block_id not in seen:
            deduped.append(block)
            seen.add(block_id)

    return deduped


def extract_question_blocks(blocks):
    candidate_blocks = [
        block
        for block in blocks
        if is_question_candidate(block["question_nums"])
    ]

    candidate_blocks = dedupe_question_blocks(candidate_blocks)

    multi_number_blocks = [
        block for block in candidate_blocks if len(block["question_nums"]) >= 2
    ]
    candidate_sets = [multi_number_blocks, candidate_blocks]

    best_blocks = []
    best_coverage = 0
    for block_set in candidate_sets:
        coverage = contiguous_question_coverage(block_set)
        if coverage > best_coverage:
            best_blocks = block_set
            best_coverage = coverage

    if best_coverage:
        best_blocks = [
            block
            for block in best_blocks
            if max(block["question_nums"]) <= best_coverage
        ]

    if best_blocks:
        covered = {num for block in best_blocks for num in block["question_nums"]}
        next_expected = max(covered)
        singleton_candidates = sorted(
            (
                block
                for block in candidate_blocks
                if len(block["question_nums"]) == 1 and block not in best_blocks
            ),
            key=lambda block: block["question_nums"][0],
        )

        for block in singleton_candidates:
            value = block["question_nums"][0]
            if value in covered:
                continue
            if value == next_expected + 1:
                best_blocks.append(block)
                covered.add(value)
                next_expected = value

    return best_blocks


def row_key(y0):
    return round(y0 / ROW_TOLERANCE) * ROW_TOLERANCE


def cluster_blocks_by_y(blocks, tolerance):
    if not blocks:
        return []

    clusters = [[block] for block in sorted(blocks, key=lambda b: b["y0"])]
    merged = [clusters[0]]

    for cluster in clusters[1:]:
        current = cluster[0]
        prev_group = merged[-1]
        prev_y = sum(block["y0"] for block in prev_group) / len(prev_group)
        if abs(current["y0"] - prev_y) <= tolerance:
            prev_group.extend(cluster)
        else:
            merged.append(cluster)

    return merged


def infer_vertical_column_count(question_blocks):
    question_rows = cluster_blocks_by_y(question_blocks, ROW_CLUSTER_TOLERANCE)
    if not question_rows:
        return 1

    return max(
        sum(len(block["question_nums"]) for block in row)
        for row in question_rows
    )


def map_vertical_merged_answer_blocks(question_blocks, answer_blocks):
    question_rows = cluster_blocks_by_y(question_blocks, ROW_CLUSTER_TOLERANCE)
    if not question_rows:
        return {}

    ordered_question_rows = []
    for row in question_rows:
        q_nums = []
        for block in sorted(row, key=lambda b: b["x0"]):
            q_nums.extend(block["question_nums"])
        ordered_question_rows.append(sorted(q_nums))

    column_count = max(len(row) for row in ordered_question_rows)
    ordered_answer_blocks = sorted(answer_blocks, key=lambda b: (b["y0"], b["x0"]))

    page_answers = {}
    row_cursor = 0
    for block in ordered_answer_blocks:
        values = block["values"]
        if len(values) < column_count or len(values) % column_count != 0:
            continue

        row_span = len(values) // column_count
        row_values = [
            values[row_idx * column_count:(row_idx + 1) * column_count]
            for row_idx in range(row_span)
        ]

        question_slice = ordered_question_rows[row_cursor:row_cursor + row_span]
        if len(question_slice) != row_span:
            break

        for q_nums, answers in zip(question_slice, row_values):
            if len(q_nums) != len(answers):
                continue
            for question, answer in zip(q_nums, answers):
                page_answers[question] = answer

        row_cursor += row_span

    return page_answers


def detect_layout(blocks, question_blocks):
    if question_blocks and looks_like_question_blocks(question_blocks):
        steps = [
            block["question_nums"][1] - block["question_nums"][0]
            for block in question_blocks
            if len(block["question_nums"]) >= 2
        ]
        if steps and round(sum(steps) / len(steps)) > 1:
            return "vertical"
        return "horizontal"

    if not blocks:
        return "horizontal"

    xs = [b["x0"] for b in blocks]
    ys = [b["y0"] for b in blocks]

    x_spread = max(xs) - min(xs)
    y_spread = max(ys) - min(ys)

    return "vertical" if x_spread > y_spread else "horizontal"


def sort_blocks(blocks, layout):
    if layout == "vertical":
        return sorted(blocks, key=lambda b: (b["x0"], b["y0"]))
    return sorted(blocks, key=lambda b: (b["y0"], b["x0"]))


def map_vertical_question_answer_blocks(question_blocks, answer_blocks):
    question_rows = cluster_blocks_by_y(question_blocks, ROW_CLUSTER_TOLERANCE)
    if not question_rows:
        return {}

    page_answers = {}
    min_question_y = min(block["y0"] for block in question_blocks) - ROW_CLUSTER_TOLERANCE
    max_question_y = max(block["y0"] for block in question_blocks) + ROW_CLUSTER_TOLERANCE
    answer_rows = cluster_blocks_by_y(
        [
            block
            for block in answer_blocks
            if min_question_y <= block["y0"] <= max_question_y
        ],
        ROW_CLUSTER_TOLERANCE,
    )

    for question_row, answer_row in zip(question_rows, answer_rows):
        q_nums = []
        for block in sorted(question_row, key=lambda b: b["x0"]):
            q_nums.extend(block["question_nums"])

        q_nums = sorted(q_nums)

        a_vals = []
        for block in sorted(answer_row, key=lambda b: b["x0"]):
            a_vals.extend(block["values"])

        if len(q_nums) != len(a_vals):
            continue

        for question, answer in zip(q_nums, a_vals):
            page_answers[question] = answer

    return page_answers


def extract_answer_key(pdf_path):
    doc = fitz.open(pdf_path)
    full_key = {}

    for page_index, page in enumerate(doc):
        page_text = page.get_text().strip()
        if not page_text and page.get_images(full=True):
            raise ValueError(
                f"Page {page_index+1}: answer key PDF is image-only. "
                "This extractor supports text-based answer-key PDFs only."
            )

        numeric_blocks = extract_numeric_blocks(page)

        if not numeric_blocks:
            raise ValueError(f"Page {page_index+1}: No numeric blocks detected")

        question_blocks = extract_question_blocks(numeric_blocks)
        answer_blocks = [block for block in numeric_blocks if block not in question_blocks]

        page_answers = {}
        layout = detect_layout(numeric_blocks, question_blocks)
        sorted_blocks = sort_blocks(numeric_blocks, layout)

        if layout == "vertical" and looks_like_question_blocks(question_blocks):
            page_answers = map_vertical_question_answer_blocks(
                question_blocks,
                answer_blocks,
            )

        if not page_answers and looks_like_question_blocks(question_blocks):
            filtered_answer_blocks = [
                block
                for block in answer_blocks
                if len(block["values"]) >= 3
                and not is_arithmetic_progression(block["question_nums"] or [])
            ]

            question_blocks_sorted = sort_blocks(question_blocks, layout)
            answer_blocks_sorted = sort_blocks(filtered_answer_blocks, layout)

            if len(question_blocks_sorted) == len(answer_blocks_sorted) and all(
                len(q_block["question_nums"]) == len(a_block["values"])
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted)
            ):
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted):
                    for question, answer in zip(q_block["question_nums"], a_block["values"]):
                        page_answers[question] = answer

        if not page_answers and layout == "vertical" and looks_like_question_blocks(question_blocks):
            min_question_y = min(block["y0"] for block in question_blocks) - ROW_CLUSTER_TOLERANCE
            max_question_y = max(block["y0"] for block in question_blocks) + ROW_CLUSTER_TOLERANCE
            vertical_answer_blocks = sort_blocks(
                [
                    block
                    for block in answer_blocks
                    if min_question_y <= block["y0"] <= max_question_y
                    and len(block["values"]) >= 2
                ],
                "horizontal",
            )
            page_answers = map_vertical_merged_answer_blocks(
                question_blocks,
                vertical_answer_blocks,
            )

        if not page_answers:
            section_answers = []

            for block in sorted_blocks:
                section_answers.extend(block["values"])

            page_answers = {i + 1: answer for i, answer in enumerate(section_answers)}

        if not page_answers:
            raise ValueError(f"Page {page_index+1}: No answers detected")

        full_key[page_index + 1] = page_answers

    return full_key
