import re

import fitz


QUESTION_NUMBER_LIMIT = 200
ROW_TOLERANCE = 2.0


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

    flat = [num for block in blocks for num in block["nums"]]
    if not flat or min(flat) != 1:
        return False

    unique = sorted(set(flat))
    return len(flat) == len(unique) and unique == list(range(1, unique[-1] + 1))


def extract_numeric_blocks(page):
    numeric_blocks = []
    for block in page.get_text("blocks"):
        nums = list(map(int, re.findall(r"\b\d+\b", block[4])))
        if not nums:
            continue

        numeric_blocks.append(
            {
                "x0": block[0],
                "y0": block[1],
                "nums": nums,
            }
        )

    return numeric_blocks


def is_question_candidate(nums):
    if not nums or max(nums) > QUESTION_NUMBER_LIMIT:
        return False

    if len(nums) == 1:
        return True

    step = nums[1] - nums[0]
    if step <= 0:
        return False

    return all(nums[i + 1] - nums[i] == step for i in range(len(nums) - 1))


def contiguous_question_coverage(blocks):
    if not blocks:
        return 0

    flat = [num for block in blocks for num in block["nums"]]
    if not flat or min(flat) != 1 or len(flat) != len(set(flat)):
        return 0

    unique = sorted(set(flat))
    expected = list(range(1, unique[-1] + 1))
    if unique != expected:
        return 0

    return unique[-1]


def extract_question_blocks(blocks):
    candidate_blocks = [block for block in blocks if is_question_candidate(block["nums"])]

    multi_number_blocks = [block for block in candidate_blocks if len(block["nums"]) >= 2]
    candidate_sets = [multi_number_blocks, candidate_blocks]

    best_blocks = []
    best_coverage = 0
    for block_set in candidate_sets:
        coverage = contiguous_question_coverage(block_set)
        if coverage > best_coverage:
            best_blocks = block_set
            best_coverage = coverage

    return best_blocks


def row_key(y0):
    return round(y0 / ROW_TOLERANCE) * ROW_TOLERANCE


def detect_layout(blocks, question_blocks):
    if question_blocks and looks_like_question_blocks(question_blocks):
        if max(len(block["nums"]) for block in question_blocks) <= 3:
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
    questions_by_row = {}
    answers_by_row = {}

    for block in question_blocks:
        questions_by_row.setdefault(row_key(block["y0"]), []).append(block)

    for block in answer_blocks:
        answers_by_row.setdefault(row_key(block["y0"]), []).append(block)

    page_answers = {}

    for y in sorted(set(questions_by_row) & set(answers_by_row)):
        q_nums = []
        for block in sorted(questions_by_row[y], key=lambda b: b["x0"]):
            q_nums.extend(block["nums"])

        q_nums = sorted(q_nums)

        a_nums = []
        for block in sorted(answers_by_row[y], key=lambda b: b["x0"]):
            a_nums.extend(block["nums"])

        if len(q_nums) != len(a_nums):
            continue

        for question, answer in zip(q_nums, a_nums):
            page_answers[question] = str(answer)

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
                if len(block["nums"]) >= 3 and not is_arithmetic_progression(block["nums"])
            ]

            question_blocks_sorted = sort_blocks(question_blocks, layout)
            answer_blocks_sorted = sort_blocks(filtered_answer_blocks, layout)

            if len(question_blocks_sorted) == len(answer_blocks_sorted) and all(
                len(q_block["nums"]) == len(a_block["nums"])
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted)
            ):
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted):
                    for question, answer in zip(q_block["nums"], a_block["nums"]):
                        page_answers[question] = str(answer)

        if not page_answers:
            section_answers = []

            for block in sorted_blocks:
                section_answers.extend(block["nums"])

            page_answers = {i + 1: str(ans) for i, ans in enumerate(section_answers)}

        if not page_answers:
            raise ValueError(f"Page {page_index+1}: No answers detected")

        full_key[page_index + 1] = page_answers

    return full_key
