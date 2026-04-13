import fitz
import re


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
        if len(nums) < 3:
            continue

        numeric_blocks.append(
            {
                "x0": block[0],
                "y0": block[1],
                "nums": nums,
            }
        )

    return numeric_blocks


# 🔥 NEW: Detect layout (horizontal vs vertical)
def detect_layout(blocks):
    if not blocks:
        return "horizontal"

    xs = [b["x0"] for b in blocks]
    ys = [b["y0"] for b in blocks]

    x_spread = max(xs) - min(xs)
    y_spread = max(ys) - min(ys)

    # If spread more in x → multiple columns → vertical layout
    return "vertical" if x_spread > y_spread else "horizontal"


# 🔥 NEW: Sort blocks based on layout
def sort_blocks(blocks, layout):
    if layout == "vertical":
        return sorted(blocks, key=lambda b: (b["x0"], b["y0"]))  # column-wise
    else:
        return sorted(blocks, key=lambda b: (b["y0"], b["x0"]))  # row-wise


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

        question_blocks = [
            block for block in numeric_blocks if is_arithmetic_progression(block["nums"])
        ]

        answer_blocks = numeric_blocks

        page_answers = {}

        # 🔥 Detect layout once
        layout = detect_layout(numeric_blocks)

        # 🔥 Sort based on layout
        sorted_blocks = sort_blocks(numeric_blocks, layout)

        # 🔥 CASE 1: Question + Answer structure detected
        if looks_like_question_blocks(question_blocks):

            answer_blocks = [
                block
                for block in numeric_blocks
                if not is_arithmetic_progression(block["nums"])
            ]

            question_blocks_sorted = sort_blocks(question_blocks, layout)
            answer_blocks_sorted = sort_blocks(answer_blocks, layout)

            if len(question_blocks_sorted) == len(answer_blocks_sorted) and all(
                len(q_block["nums"]) == len(a_block["nums"])
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted)
            ):
                for q_block, a_block in zip(question_blocks_sorted, answer_blocks_sorted):
                    for question, answer in zip(q_block["nums"], a_block["nums"]):
                        page_answers[question] = str(answer)

        # 🔥 CASE 2: Fallback (pure answers, no question numbers)
        if not page_answers:
            section_answers = []

            for block in sorted_blocks:
                section_answers.extend(block["nums"])

            # Map sequentially
            page_answers = {i + 1: str(ans) for i, ans in enumerate(section_answers)}

        if not page_answers:
            raise ValueError(f"Page {page_index+1}: No answers detected")

        full_key[page_index + 1] = page_answers

    return full_key