import csv
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output" / "boxes"
DEBUG_DIR = OUTPUT_DIR / "_debug"
RENDERED_INPUT_DIR = OUTPUT_DIR / "_input_rendered"

# Set True to wipe previous box output on each run
CLEAR_OUTPUT = True
PDF_RENDER_ZOOM = 2.0

# Numbering behavior
GLOBAL_NUMBERING = False
GLOBAL_START = 1
ROW_PAGE_START_QUESTION = {
    "answer_sheet_pg_1": 1,
    "answer_sheet_pg_2": 1,
}
COL_PAGE_START_QUESTION = {
    "paper_pg_1": 1,
    "paper_pg_2": 1,
}
PAGE_STEM_RE = re.compile(r"^(?P<prefix>.+)_pg_(?P<page>\d+)$")

# Shared preprocessing
ADAPTIVE_BLOCK = 31
ADAPTIVE_C = 12
DESKEW = True
DESKEW_MAX_ANGLE = 8.0

# Row-layout tuning
ROW_H_LINE_SCALE = 35
ROW_V_LINE_SCALE = 35
ROW_LINE_THRESH_RATIO = 0.15
ROW_VERT_LINE_MIN_HEIGHT_PCT = 0.6
ROW_BAND_MIN_HEIGHT = 20
ROW_BAND_MAX_HEIGHT = 60
ROW_MIN_BAND_INK = 250
ROW_IGNORE_TOP_PCT = 0.12
ROW_PAD_X = 2
ROW_PAD_Y = 0
ROW_BAND_PAD_TOP = 3
ROW_BAND_PAD_BOTTOM = 3

# Column-layout tuning
COL_H_LINE_SCALE = 25
COL_V_LINE_SCALE = 30
COL_ROW_LINE_THRESH_RATIO = 0.03
COL_BAND_MIN_HEIGHT = 10
COL_BAND_MAX_HEIGHT = 70
COL_MIN_BAND_INK = 50
COL_IGNORE_TOP_PCT = 0.05
COL_PAD_X = 2
COL_PAD_Y = 0
COL_BAND_PAD_TOP = 2
COL_BAND_PAD_BOTTOM = 2
EXPECTED_ROWS = 30
EXPECTED_ANSWER_COLS = 4
MIN_ANSWER_X_FRAC = 0.20
WIDEST_BANDS_KEEP = 4
COL_SUB_BAND_MIN_WIDTH = 40
COL_REF_LINE_EDGE_TOL = 6

# Auto-detection tuning
ROW_GAP_CV_MAX = 0.18
ROW_GAP_CLOSE_TOL_PCT = 0.25
ROW_GAP_CLOSE_TOL_MIN = 3
ROW_MIN_UNIFORM_GAP_RATIO = 0.75
ROW_MIN_MATCHED_ROW_RATIO = 0.75
MIN_COL_LAYOUT_ANSWER_BANDS = 2
MIN_COL_LAYOUT_ROWS = 10
MIN_PAGE_INK_RATIO = 0.01
MIN_PAGE_GRID_RATIO = 0.005
MIN_PAGE_VERTICAL_GRID_RATIO = 0.003
ROW_UNIFORM_FALLBACK_TALL_MULT = 1.45
ROW_UNIFORM_FALLBACK_SHORT_MULT = 0.55
ROW_UNIFORM_FALLBACK_SHORT_RATIO = 0.20
LOCAL_ROW_ANCHOR_TOL_ROWS = 1.5
COL_TRACE_ROW_LINE_THRESH_RATIO = 0.06
COL_TRACE_CLOSE_LINE_GAP_RATIO = 0.45


@dataclass
class RowLayoutCandidate:
    bands: list
    ref_lines: list
    gap_cv: float
    gap_close_ratio: float
    matched_rows: int
    matched_row_ratio: float
    v_lines: np.ndarray | None
    valid: bool

    @property
    def num_cols(self):
        return max(len(self.ref_lines) - 1, 0)


@dataclass
class ColLayoutCandidate:
    row_bands: list
    answer_bands: list
    column_row_bands: list
    valid: bool


def _adaptive_bin(gray):
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        ADAPTIVE_BLOCK,
        ADAPTIVE_C,
    )


def _deskew_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    h, w = gray.shape
    min_len = int(w * 0.35)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=min_len,
        maxLineGap=20,
    )
    if lines is None:
        return img, 0.0

    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        while angle <= -90:
            angle += 180
        while angle > 90:
            angle -= 180
        if abs(angle) <= 30:
            angles.append(angle)

    if not angles:
        return img, 0.0

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.1:
        return img, 0.0

    median_angle = max(-DESKEW_MAX_ANGLE, min(DESKEW_MAX_ANGLE, median_angle))
    angle = -median_angle
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2.0) - center[0]
    matrix[1, 2] += (new_h / 2.0) - center[1]

    rotated = cv2.warpAffine(
        img,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, angle


def _detect_grid_lines(bw, img_w, img_h, h_scale, v_scale):
    h_len = max(20, img_w // h_scale)
    v_len = max(20, img_h // v_scale)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    h_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, v_kernel)
    return h_lines, v_lines


def _row_bands_from_lines(
    h_lines,
    ink,
    img_h,
    img_w,
    line_thresh_ratio,
    band_min_height,
    band_max_height,
    min_band_ink,
    ignore_top_pct,
):
    row_sum = h_lines.sum(axis=1) / 255.0
    thr = img_w * line_thresh_ratio
    peaks = [i for i, value in enumerate(row_sum) if value > thr]

    ranges = []
    for idx in peaks:
        if not ranges or idx > ranges[-1][1] + 1:
            ranges.append([idx, idx])
        else:
            ranges[-1][1] = idx

    ys = [(start + end) // 2 for start, end in ranges]
    ys = [0] + ys + [img_h - 1]
    ys = sorted(set(ys))

    bands = []
    top_ignore = int(img_h * ignore_top_pct)
    for i in range(len(ys) - 1):
        y0, y1 = ys[i], ys[i + 1]
        band_h = y1 - y0
        if band_h < band_min_height or band_h > band_max_height:
            continue
        if y0 < top_ignore:
            continue
        band_ink = cv2.countNonZero(ink[y0:y1, :])
        if band_ink < min_band_ink:
            continue
        bands.append((y0, y1))
    return bands


def _line_positions_in_band(v_lines, y0, y1, min_height_pct):
    band = v_lines[y0:y1, :]
    col_sum = band.sum(axis=0) / 255.0
    thr = (y1 - y0) * min_height_pct
    cols = np.where(col_sum > thr)[0]

    ranges = []
    for c in cols:
        if not ranges or c > ranges[-1][1] + 1:
            ranges.append([c, c])
        else:
            ranges[-1][1] = c

    return [(start + end) // 2 for start, end in ranges]


def _pick_reference_lines(v_lines, bands, img_h, min_height_pct):
    line_sets = []
    for y0, y1 in bands:
        lines = _line_positions_in_band(v_lines, y0, y1, min_height_pct)
        if len(lines) >= 5:
            line_sets.append(lines)

    if line_sets:
        return max(line_sets, key=len)

    col_sum = v_lines.sum(axis=0) / 255.0
    thr = img_h * 0.4
    cols = np.where(col_sum > thr)[0]
    ranges = []
    for c in cols:
        if not ranges or c > ranges[-1][1] + 1:
            ranges.append([c, c])
        else:
            ranges[-1][1] = c
    return [(start + end) // 2 for start, end in ranges]


def _col_bands_from_lines(v_lines, img_h):
    col_sum = v_lines.sum(axis=0) / 255.0
    thr = img_h * COL_ROW_LINE_THRESH_RATIO
    peaks = [i for i, value in enumerate(col_sum) if value > thr]

    ranges = []
    for idx in peaks:
        if not ranges or idx > ranges[-1][1] + 1:
            ranges.append([idx, idx])
        else:
            ranges[-1][1] = idx

    xs = [(start + end) // 2 for start, end in ranges]
    xs = [0] + xs
    return sorted(set(xs))


def _column_spans(col_lines, img_w):
    xs = sorted(set(col_lines + [img_w - 1]))
    spans = []
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x1 - x0 < COL_BAND_MIN_HEIGHT:
            continue
        spans.append((x0, x1))
    return spans


def _select_answer_bands(col_bands, img_w):
    if not col_bands:
        return []

    widths = np.array([x1 - x0 for x0, x1 in col_bands], dtype=np.int32)
    min_x = img_w * MIN_ANSWER_X_FRAC

    if len(widths) >= 2:
        sorted_widths = np.sort(widths)
        gaps = np.diff(sorted_widths)
        gap_idx = int(np.argmax(gaps))
        narrow = sorted_widths[: gap_idx + 1]
        wide = sorted_widths[gap_idx + 1 :]
        if narrow.size and wide.size and wide.mean() >= narrow.mean() * 1.4:
            wide_thr = (sorted_widths[gap_idx] + sorted_widths[gap_idx + 1]) / 2.0
            wide_mask = widths >= wide_thr
            answers = []
            run_start = None
            for idx, is_wide in enumerate(wide_mask):
                if is_wide:
                    if run_start is None:
                        run_start = idx
                    continue
                if run_start is not None:
                    answers.append((col_bands[run_start][0], col_bands[idx - 1][1]))
                    run_start = None
            if run_start is not None:
                answers.append((col_bands[run_start][0], col_bands[len(col_bands) - 1][1]))

            answers = [band for band in answers if band[1] > min_x]
            if answers:
                return answers

    candidates = [band for band in col_bands if band[1] > min_x]
    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda band: ((band[1] - band[0]), band[1]),
        reverse=True,
    )
    return sorted(ranked[:WIDEST_BANDS_KEEP], key=lambda band: band[0])


def _normalize_row_bands(bands):
    bands = sorted(bands, key=lambda band: band[0])
    if EXPECTED_ROWS <= 0 or len(bands) <= EXPECTED_ROWS:
        return bands

    target_height = _estimate_row_target_height(bands)
    best_window = bands[:EXPECTED_ROWS]
    best_score = None
    for start in range(len(bands) - EXPECTED_ROWS + 1):
        window = bands[start : start + EXPECTED_ROWS]
        heights = np.array([y1 - y0 for y0, y1 in window], dtype=np.float32)
        gaps = np.array(
            [window[i + 1][0] - window[i][0] for i in range(len(window) - 1)],
            dtype=np.float32,
        )
        score = float(np.var(heights) + np.mean(np.abs(heights - target_height)))
        if len(gaps):
            score += float(np.var(gaps) + np.mean(np.abs(gaps - target_height)))
        # Prefer runs that keep the bottom-most rows; header noise is usually on top.
        score += (bands[-1][1] - window[-1][1]) * 0.02
        if best_score is None or score < best_score:
            best_score = score
            best_window = window
    return best_window


def _estimate_row_target_height(bands, table_y0=None, table_y1=None):
    if not bands:
        return float(COL_BAND_MIN_HEIGHT)

    if EXPECTED_ROWS > 0:
        if table_y0 is not None and table_y1 is not None and table_y1 > table_y0:
            return max(
                float((table_y1 - table_y0) / EXPECTED_ROWS),
                float(COL_BAND_MIN_HEIGHT),
            )
        span = bands[-1][1] - bands[0][0]
        if span > 0:
            return max(float(span / EXPECTED_ROWS), float(COL_BAND_MIN_HEIGHT))

    heights = np.array([y1 - y0 for y0, y1 in bands if y1 > y0], dtype=np.float32)
    if not len(heights):
        return float(COL_BAND_MIN_HEIGHT)
    return max(float(np.median(heights)), float(COL_BAND_MIN_HEIGHT))


def _split_band_equally(y0, y1, pieces):
    pieces = max(int(pieces), 1)
    edges = np.linspace(y0, y1, pieces + 1)
    result = []
    for start, end in zip(edges[:-1], edges[1:]):
        start_i = int(round(start))
        end_i = int(round(end))
        if end_i > start_i:
            result.append((start_i, end_i))
    return result


def _regularize_row_bands(bands, table_y0=None, table_y1=None):
    bands = sorted(bands, key=lambda band: band[0])
    if not bands:
        return bands
    if EXPECTED_ROWS > 0 and len(bands) >= EXPECTED_ROWS:
        return _normalize_row_bands(bands)

    target_height = _estimate_row_target_height(bands, table_y0, table_y1)

    expanded = []
    cursor = None
    for y0, y1 in bands:
        if cursor is not None:
            gap = y0 - cursor
            if gap >= target_height * 1.35:
                expanded.extend(_split_band_equally(cursor, y0, int(max(1, round(gap / target_height)))))

        height = y1 - y0
        if height >= target_height * 1.35:
            expanded.extend(_split_band_equally(y0, y1, int(max(1, round(height / target_height)))))
        else:
            expanded.append((y0, y1))
        cursor = y1

    if cursor is not None and table_y1 is not None:
        gap = table_y1 - cursor
        if gap >= target_height * 0.75:
            expanded.extend(_split_band_equally(cursor, table_y1, int(max(1, round(gap / target_height)))))

    expanded = _consolidate_row_bands(expanded, target_height)
    if EXPECTED_ROWS > 0 and len(expanded) < EXPECTED_ROWS:
        while len(expanded) < EXPECTED_ROWS:
            heights = [y1 - y0 for y0, y1 in expanded]
            if not heights:
                break
            split_idx = int(np.argmax(heights))
            y0, y1 = expanded[split_idx]
            if (y1 - y0) < target_height * 1.2:
                break
            replacement = _split_band_equally(y0, y1, 2)
            expanded = expanded[:split_idx] + replacement + expanded[split_idx + 1 :]

    return _normalize_row_bands(expanded)


def _consolidate_row_bands(bands, target_height):
    bands = sorted(bands, key=lambda band: band[0])
    if not bands:
        return bands

    merged = []
    start, end = bands[0]
    for next_start, next_end in bands[1:]:
        if next_start - end > target_height * 0.6:
            merged.append((start, end))
            start, end = next_start, next_end
            continue

        current_height = end - start
        merged_height = next_end - start
        if (
            current_height >= target_height * 0.75
            and abs(current_height - target_height) <= abs(merged_height - target_height)
        ):
            merged.append((start, end))
            start, end = next_start, next_end
            continue

        end = next_end

    merged.append((start, end))
    return merged


def _row_bands_need_uniform_fallback(row_bands, table_y0=None, table_y1=None):
    if EXPECTED_ROWS <= 0 or not row_bands:
        return False
    if table_y0 is None or table_y1 is None or table_y1 <= table_y0:
        return False

    target_height = max(float((table_y1 - table_y0) / EXPECTED_ROWS), float(COL_BAND_MIN_HEIGHT))
    heights = np.array([y1 - y0 for y0, y1 in row_bands if y1 > y0], dtype=np.float32)
    if not len(heights):
        return True

    too_tall = int(np.sum(heights > (target_height * ROW_UNIFORM_FALLBACK_TALL_MULT)))
    too_short = int(np.sum(heights < (target_height * ROW_UNIFORM_FALLBACK_SHORT_MULT)))
    if len(row_bands) != EXPECTED_ROWS:
        return True
    if too_tall > 0:
        return True
    if too_short > max(1, int(round(len(row_bands) * ROW_UNIFORM_FALLBACK_SHORT_RATIO))):
        return True
    return False


def _column_row_bands_from_local_grid(h_lines, v_lines, answer_bands, fallback_row_bands):
    if not answer_bands:
        return []

    row_count = len(fallback_row_bands)
    if EXPECTED_ROWS <= 0 or row_count <= 0:
        return [fallback_row_bands for _ in answer_bands]

    global_y0 = int(fallback_row_bands[0][0])
    global_y1 = int(fallback_row_bands[-1][1])
    target_h = max(float(global_y1 - global_y0) / row_count, 1.0)
    max_anchor_delta = int(round(target_h * LOCAL_ROW_ANCHOR_TOL_ROWS))
    min_span = int(round(target_h * row_count * 0.9))
    max_span = int(round(target_h * row_count * 1.1))

    per_column = []
    for x0, x1 in answer_bands:
        if x1 <= x0:
            per_column.append(fallback_row_bands)
            continue

        sub_h = h_lines[:, x0:x1]
        sub_v = v_lines[:, x0:x1]
        sub_grid = cv2.bitwise_or(sub_h, sub_v)
        points = cv2.findNonZero(sub_grid)
        if points is None:
            per_column.append(fallback_row_bands)
            continue

        _, local_y0, _, local_h = cv2.boundingRect(points)
        local_y1 = local_y0 + local_h
        if local_y1 <= local_y0 or local_h < EXPECTED_ROWS:
            per_column.append(fallback_row_bands)
            continue

        # Keep local column mapping anchored near the globally-detected table rows.
        local_y0 = int(np.clip(local_y0, global_y0 - max_anchor_delta, global_y0 + max_anchor_delta))
        local_y1 = int(np.clip(local_y1, global_y1 - max_anchor_delta, global_y1 + max_anchor_delta))
        span = local_y1 - local_y0
        if span < min_span or span > max_span:
            per_column.append(fallback_row_bands)
            continue

        local_rows = _trace_column_row_bands_from_h_lines(
            sub_h,
            x1 - x0,
            row_count,
            int(local_y0),
            int(local_y1),
        )
        if not local_rows:
            local_rows = _split_band_equally(int(local_y0), int(local_y1), EXPECTED_ROWS)
        if len(local_rows) != row_count:
            per_column.append(fallback_row_bands)
            continue
        per_column.append(local_rows)

    return per_column


def _horizontal_line_positions(h_lines, img_w, line_thresh_ratio):
    row_sum = h_lines.sum(axis=1) / 255.0
    thr = img_w * line_thresh_ratio
    peaks = np.where(row_sum > thr)[0]
    if not len(peaks):
        return []

    ranges = []
    for idx in peaks:
        if not ranges or idx > ranges[-1][1] + 1:
            ranges.append([int(idx), int(idx)])
        else:
            ranges[-1][1] = int(idx)
    return [int((start + end) // 2) for start, end in ranges]


def _merge_close_positions(positions, max_gap):
    if not positions:
        return []

    positions = sorted(int(pos) for pos in positions)
    merged = []
    cluster = [positions[0]]
    for pos in positions[1:]:
        if pos - cluster[-1] <= max_gap:
            cluster.append(pos)
        else:
            merged.append(int(round(float(sum(cluster)) / len(cluster))))
            cluster = [pos]
    merged.append(int(round(float(sum(cluster)) / len(cluster))))
    return merged


def _trace_column_row_bands_from_h_lines(h_lines, img_w, row_count, anchor_y0, anchor_y1):
    if row_count <= 0 or anchor_y1 <= anchor_y0:
        return []

    line_positions = _horizontal_line_positions(
        h_lines,
        img_w,
        COL_TRACE_ROW_LINE_THRESH_RATIO,
    )
    if len(line_positions) < row_count + 1:
        return []

    target_h = max(float(anchor_y1 - anchor_y0) / row_count, 1.0)
    merge_gap = max(3, int(round(target_h * COL_TRACE_CLOSE_LINE_GAP_RATIO)))
    line_positions = _merge_close_positions(line_positions, merge_gap)
    if len(line_positions) < row_count + 1:
        return []

    expected_span = float(anchor_y1 - anchor_y0)
    best_window = None
    best_score = None
    for start in range(len(line_positions) - row_count):
        window = line_positions[start : start + row_count + 1]
        gaps = np.diff(window).astype(np.float32)
        score = float(np.var(gaps) + np.mean(np.abs(gaps - target_h)))
        score += abs(window[0] - anchor_y0) * 0.35
        score += abs(window[-1] - anchor_y1) * 0.35
        score += abs((window[-1] - window[0]) - expected_span) * 0.25
        if best_score is None or score < best_score:
            best_score = score
            best_window = window

    if best_window is None:
        return []

    max_anchor_delta = max(4, int(round(target_h * LOCAL_ROW_ANCHOR_TOL_ROWS)))
    if abs(best_window[0] - anchor_y0) > max_anchor_delta:
        return []
    if abs(best_window[-1] - anchor_y1) > max_anchor_delta:
        return []

    row_bands = []
    for upper, lower in zip(best_window[:-1], best_window[1:]):
        if lower <= upper:
            return []
        row_bands.append((int(upper), int(lower)))

    return row_bands if len(row_bands) == row_count else []


def _normalize_answer_bands(answer_bands):
    answer_bands = sorted(answer_bands, key=lambda band: band[0])
    if EXPECTED_ANSWER_COLS <= 0 or len(answer_bands) <= EXPECTED_ANSWER_COLS:
        return answer_bands

    ranked = sorted(
        answer_bands,
        key=lambda band: ((band[1] - band[0]), band[1]),
        reverse=True,
    )
    trimmed = ranked[:EXPECTED_ANSWER_COLS]
    return sorted(trimmed, key=lambda band: band[0])


def _estimate_answer_band_width(answer_bands, ref_lines=None):
    widths = [x1 - x0 for x0, x1 in answer_bands if x1 > x0]
    if widths:
        return float(np.median(widths))

    if ref_lines and len(ref_lines) >= 2:
        ref_widths = np.array(
            [int(ref_lines[idx + 1]) - int(ref_lines[idx]) for idx in range(len(ref_lines) - 1)],
            dtype=np.int32,
        )
        ref_widths = ref_widths[ref_widths > 0]
        if len(ref_widths):
            upper_half = ref_widths[ref_widths >= np.percentile(ref_widths, 50)]
            if len(upper_half):
                return float(np.median(upper_half))
            return float(np.median(ref_widths))

    return 0.0


def _answer_bands_from_ref_lines(ref_lines):
    if not ref_lines or len(ref_lines) < 4:
        return []

    intervals = [
        (int(ref_lines[idx]), int(ref_lines[idx + 1]))
        for idx in range(len(ref_lines) - 1)
    ]
    widths = np.array([x1 - x0 for x0, x1 in intervals], dtype=np.int32)
    widths = widths[widths > 0]
    if len(widths) < 3:
        return []

    gap_max = max(8, int(np.percentile(widths, 10) * 2.0))
    narrow_max = max(20, min(40, int(np.percentile(widths, 35) * 1.8)))

    answers = []
    idx = 0
    while idx < len(intervals):
        width = intervals[idx][1] - intervals[idx][0]
        if width <= gap_max:
            idx += 1
            continue

        if width <= narrow_max:
            content = []
            scan = idx + 1
            while scan < len(intervals):
                scan_width = intervals[scan][1] - intervals[scan][0]
                if scan_width <= gap_max:
                    break
                if len(content) >= 2 and scan_width <= narrow_max:
                    break
                content.append(intervals[scan])
                scan += 1

            if len(content) >= 2:
                answers.append(content[1])
                idx = scan
                continue

        idx += 1

    return _normalize_answer_bands(answers)


def _pick_refined_segment(segments, expected_width):
    if not segments:
        return None
    if expected_width <= 0:
        return segments[-1]

    return min(
        segments,
        key=lambda segment: (
            abs((segment[1] - segment[0]) - expected_width),
            -segment[0],
        ),
    )


def _refine_answer_bands(answer_bands, ref_lines, expected_width=0.0):
    if not answer_bands or not ref_lines:
        return answer_bands

    ref_positions = sorted({int(line) for line in ref_lines})
    refined = []
    for x0, x1 in answer_bands:
        inner_lines = [
            line
            for line in ref_positions
            if (x0 + COL_REF_LINE_EDGE_TOL) < line < (x1 - COL_REF_LINE_EDGE_TOL)
        ]
        boundaries = sorted(set([x0] + inner_lines + [x1]))
        segments = []
        for left, right in zip(boundaries, boundaries[1:]):
            if right - left >= COL_SUB_BAND_MIN_WIDTH:
                segments.append((left, right))

        picked = _pick_refined_segment(segments, expected_width)
        if picked is not None:
            refined.append(picked)
            continue
        refined.append((x0, x1))

    return _normalize_answer_bands(refined)


def _build_row_candidate(bw, img_h, img_w):
    h_lines, v_lines = _detect_grid_lines(
        bw,
        img_w,
        img_h,
        ROW_H_LINE_SCALE,
        ROW_V_LINE_SCALE,
    )
    grid = cv2.bitwise_or(h_lines, v_lines)
    ink = cv2.bitwise_and(bw, cv2.bitwise_not(grid))

    bands = _row_bands_from_lines(
        h_lines,
        ink,
        img_h,
        img_w,
        ROW_LINE_THRESH_RATIO,
        ROW_BAND_MIN_HEIGHT,
        ROW_BAND_MAX_HEIGHT,
        ROW_MIN_BAND_INK,
        ROW_IGNORE_TOP_PCT,
    )
    if not bands:
        return RowLayoutCandidate([], [], float("inf"), 0.0, 0, 0.0, None, False)

    ref_lines = sorted(
        _pick_reference_lines(v_lines, bands, img_h, ROW_VERT_LINE_MIN_HEIGHT_PCT)
    )
    if len(ref_lines) < 2:
        return RowLayoutCandidate(
            bands,
            ref_lines,
            float("inf"),
            0.0,
            0,
            0.0,
            v_lines,
            False,
        )

    gaps = np.diff(ref_lines)
    gap_cv = float(np.std(gaps) / np.mean(gaps)) if len(gaps) and np.mean(gaps) else float("inf")
    if len(gaps):
        median_gap = float(np.median(gaps))
        tol = max(ROW_GAP_CLOSE_TOL_MIN, median_gap * ROW_GAP_CLOSE_TOL_PCT)
        gap_close_ratio = float(np.mean(np.abs(gaps - median_gap) <= tol))
    else:
        gap_close_ratio = 0.0
    row_counts = [
        len(_line_positions_in_band(v_lines, y0, y1, ROW_VERT_LINE_MIN_HEIGHT_PCT))
        for y0, y1 in bands
    ]
    matched_rows = sum(1 for count in row_counts if count == len(ref_lines))
    matched_row_ratio = float(matched_rows / len(bands)) if bands else 0.0

    return RowLayoutCandidate(
        bands,
        ref_lines,
        gap_cv,
        gap_close_ratio,
        matched_rows,
        matched_row_ratio,
        v_lines,
        True,
    )


def _build_col_candidate(bw, img_h, img_w, ref_lines=None):
    h_lines, v_lines = _detect_grid_lines(
        bw,
        img_w,
        img_h,
        COL_H_LINE_SCALE,
        COL_V_LINE_SCALE,
    )
    grid = cv2.bitwise_or(h_lines, v_lines)
    ink = cv2.bitwise_and(bw, cv2.bitwise_not(grid))
    grid_points = cv2.findNonZero(grid)
    table_y0 = None
    table_y1 = None
    if grid_points is not None:
        _, table_y0, _, table_h = cv2.boundingRect(grid_points)
        table_y1 = table_y0 + table_h

    row_band_candidates = _row_bands_from_lines(
        h_lines,
        ink,
        img_h,
        img_w,
        COL_ROW_LINE_THRESH_RATIO,
        COL_BAND_MIN_HEIGHT,
        COL_BAND_MAX_HEIGHT,
        COL_MIN_BAND_INK,
        COL_IGNORE_TOP_PCT,
    )
    if row_band_candidates:
        first_row_top = row_band_candidates[0][0]
        last_row_bottom = row_band_candidates[-1][1]
        if table_y0 is None:
            table_y0 = first_row_top
        else:
            table_y0 = max(table_y0, first_row_top)
        if table_y1 is not None:
            table_y1 = max(table_y1, last_row_bottom)

    row_bands = _regularize_row_bands(row_band_candidates, table_y0, table_y1)
    if _row_bands_need_uniform_fallback(row_bands, table_y0, table_y1):
        row_bands = _split_band_equally(int(table_y0), int(table_y1), EXPECTED_ROWS)
    col_lines = _col_bands_from_lines(v_lines, img_h)
    col_spans = _column_spans(col_lines, img_w)
    answer_bands = _answer_bands_from_ref_lines(ref_lines)
    if len(answer_bands) < EXPECTED_ANSWER_COLS:
        fallback_bands = _normalize_answer_bands(_select_answer_bands(col_spans, img_w))
        expected_width = _estimate_answer_band_width(answer_bands, ref_lines)
        fallback_bands = _refine_answer_bands(fallback_bands, ref_lines, expected_width)
        if len(fallback_bands) >= EXPECTED_ANSWER_COLS or len(fallback_bands) > len(answer_bands):
            answer_bands = fallback_bands
        elif fallback_bands:
            answer_bands = _normalize_answer_bands(
                sorted(
                    {(int(x0), int(x1)) for x0, x1 in answer_bands + fallback_bands},
                    key=lambda band: band[0],
                )
            )

    column_row_bands = _column_row_bands_from_local_grid(
        h_lines,
        v_lines,
        answer_bands,
        row_bands,
    )
    valid = bool(row_bands and answer_bands)
    return ColLayoutCandidate(row_bands, answer_bands, column_row_bands, valid)


def _choose_layout(row_candidate, col_candidate):
    row_confident = (
        row_candidate.valid
        and row_candidate.gap_close_ratio >= ROW_MIN_UNIFORM_GAP_RATIO
        and row_candidate.matched_row_ratio >= ROW_MIN_MATCHED_ROW_RATIO
    )
    col_confident = (
        col_candidate.valid
        and len(col_candidate.answer_bands) >= MIN_COL_LAYOUT_ANSWER_BANDS
        and len(col_candidate.row_bands) >= MIN_COL_LAYOUT_ROWS
    )

    if row_confident and not col_confident:
        return "row"

    if col_confident and not row_confident:
        return "col"

    if (
        col_confident
        and row_candidate.gap_cv > ROW_GAP_CV_MAX
    ):
        return "col"

    if row_candidate.valid and (
        row_candidate.gap_cv <= ROW_GAP_CV_MAX
        or row_candidate.gap_close_ratio >= ROW_MIN_UNIFORM_GAP_RATIO
    ):
        return "row"

    if col_candidate.valid and len(col_candidate.row_bands) < MIN_COL_LAYOUT_ROWS:
        return "row" if row_candidate.valid else "col"

    if col_confident:
        return "col"

    if row_candidate.valid:
        return "row"

    if col_candidate.valid:
        return "col"

    return None


def _has_table_structure(bw, img_h, img_w):
    total_pixels = float(img_h * img_w)
    if total_pixels <= 0:
        return False

    ink_ratio = cv2.countNonZero(bw) / total_pixels
    if ink_ratio < MIN_PAGE_INK_RATIO:
        return False

    h_lines, v_lines = _detect_grid_lines(
        bw,
        img_w,
        img_h,
        COL_H_LINE_SCALE,
        COL_V_LINE_SCALE,
    )
    grid_ratio = cv2.countNonZero(cv2.bitwise_or(h_lines, v_lines)) / total_pixels
    if grid_ratio < MIN_PAGE_GRID_RATIO:
        return False

    vertical_ratio = cv2.countNonZero(v_lines) / total_pixels
    return vertical_ratio >= MIN_PAGE_VERTICAL_GRID_RATIO


def _question_start_for_page(stem, layout, num_cols, row_count, global_state):
    page_question_count = max(num_cols * row_count, 0)

    if GLOBAL_NUMBERING:
        start = global_state["current"]
        global_state["current"] += page_question_count
        return start

    page_starts = (
        ROW_PAGE_START_QUESTION if layout == "row" else COL_PAGE_START_QUESTION
    )
    if stem in page_starts:
        start = page_starts[stem]
    else:
        page_match = PAGE_STEM_RE.match(stem)
        if page_match:
            group_key = (layout, page_match.group("prefix"))
            page_number = int(page_match.group("page"))
            grouped_starts = global_state.setdefault("grouped_page_starts", {})
            if page_number <= 1:
                start = 1
            else:
                start = grouped_starts.get(group_key, 1)
            grouped_starts[group_key] = start + page_question_count
            return start
        start = 1

    page_match = PAGE_STEM_RE.match(stem)
    if page_match:
        group_key = (layout, page_match.group("prefix"))
        global_state.setdefault("grouped_page_starts", {})[group_key] = (
            start + page_question_count
        )
    return start


def _crop_row_layout(img, image_path, candidate, csv_rows, global_state):
    img_h, img_w = img.shape[:2]
    start_q = _question_start_for_page(
        image_path.stem,
        "row",
        candidate.num_cols,
        len(candidate.bands),
        global_state,
    )

    out_dir = OUTPUT_DIR / image_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    debug = img.copy()

    for r_idx, (y0, y1) in enumerate(sorted(candidate.bands, key=lambda band: band[0])):
        row_lines = _line_positions_in_band(
            candidate.v_lines,
            y0,
            y1,
            ROW_VERT_LINE_MIN_HEIGHT_PCT,
        )
        lines = candidate.ref_lines
        if len(row_lines) == len(candidate.ref_lines):
            lines = sorted(row_lines)

        y0b = max(y0 - ROW_BAND_PAD_TOP, 0)
        y1b = min(y1 + ROW_BAND_PAD_BOTTOM, img_h - 1)

        for c_idx in range(len(lines) - 1):
            x0 = lines[c_idx]
            x1 = lines[c_idx + 1]

            x0p = max(x0 + ROW_PAD_X, 0)
            x1p = min(x1 - ROW_PAD_X, img_w - 1)
            y0p = max(y0b + ROW_PAD_Y, 0)
            y1p = min(y1b - ROW_PAD_Y, img_h - 1)
            if x1p <= x0p or y1p <= y0p:
                continue

            q_num = start_q + (r_idx * candidate.num_cols) + c_idx
            out_name = f"q{q_num:03d}_r{r_idx + 1:02d}_c{c_idx + 1:02d}.png"
            out_path = out_dir / out_name
            crop = img[y0p:y1p, x0p:x1p]
            if not cv2.imwrite(str(out_path), crop):
                print("Failed to write:", out_path)
                continue

            csv_rows.append(
                ["row", image_path.name, r_idx + 1, c_idx + 1, q_num, str(out_path)]
            )
            cv2.rectangle(debug, (x0p, y0p), (x1p, y1p), (0, 255, 0), 1)

    return debug


def _crop_col_layout(img, image_path, candidate, csv_rows, global_state):
    img_h, img_w = img.shape[:2]
    row_bands = sorted(candidate.row_bands, key=lambda band: band[0])
    answer_bands = sorted(candidate.answer_bands, key=lambda band: band[0])
    column_row_bands = candidate.column_row_bands or []
    row_count = len(row_bands)
    start_q = _question_start_for_page(
        image_path.stem,
        "col",
        len(answer_bands),
        row_count,
        global_state,
    )

    out_dir = OUTPUT_DIR / image_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    debug = img.copy()

    for y0, y1 in row_bands:
        cv2.line(debug, (0, y0), (img_w - 1, y0), (140, 140, 140), 1)
        cv2.line(debug, (0, y1), (img_w - 1, y1), (140, 140, 140), 1)
    for x0, x1 in answer_bands:
        cv2.line(debug, (x0, 0), (x0, img_h - 1), (255, 200, 0), 1)
        cv2.line(debug, (x1, 0), (x1, img_h - 1), (255, 200, 0), 1)

    for c_idx, (x0, x1) in enumerate(answer_bands):
        rows_for_col = row_bands
        if c_idx < len(column_row_bands):
            local_rows = column_row_bands[c_idx]
            if len(local_rows) == row_count:
                rows_for_col = local_rows

        for y0, y1 in rows_for_col:
            cv2.line(debug, (x0, y0), (x1, y0), (0, 255, 255), 1)
            cv2.line(debug, (x0, y1), (x1, y1), (0, 255, 255), 1)

        for r_idx, (y0, y1) in enumerate(rows_for_col):
            y0b = max(y0 - COL_BAND_PAD_TOP, 0)
            y1b = min(y1 + COL_BAND_PAD_BOTTOM, img_h - 1)
            x0p = max(x0 + COL_PAD_X, 0)
            x1p = min(x1 - COL_PAD_X, img_w - 1)
            y0p = max(y0b + COL_PAD_Y, 0)
            y1p = min(y1b - COL_PAD_Y, img_h - 1)
            if x1p <= x0p or y1p <= y0p:
                continue

            q_num = start_q + (c_idx * row_count) + r_idx
            out_name = f"q{q_num:03d}_r{r_idx + 1:02d}_c{c_idx + 1:02d}.png"
            out_path = out_dir / out_name
            crop = img[y0p:y1p, x0p:x1p]
            if not cv2.imwrite(str(out_path), crop):
                print("Failed to write:", out_path)
                continue

            csv_rows.append(
                ["col", image_path.name, r_idx + 1, c_idx + 1, q_num, str(out_path)]
            )
            cv2.rectangle(debug, (x0p, y0p), (x1p, y1p), (0, 255, 0), 1)

    return debug


def process_image(image_path, csv_rows, global_state):
    img = cv2.imread(str(image_path))
    if img is None:
        print("Skipped (could not read):", image_path)
        return

    if DESKEW:
        img, angle = _deskew_image(img)
        if abs(angle) > 0.01:
            print(f"Deskewed {image_path.name}: {angle:.2f} deg")

    img_h, img_w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    bw = _adaptive_bin(gray)
    if not _has_table_structure(bw, img_h, img_w):
        print("Skipped (blank/low-structure page):", image_path.name)
        return

    row_candidate = _build_row_candidate(bw, img_h, img_w)
    col_candidate = _build_col_candidate(bw, img_h, img_w, row_candidate.ref_lines)
    layout = _choose_layout(row_candidate, col_candidate)

    if layout is None:
        print("No supported layout found:", image_path.name)
        return

    dbg_dir = DEBUG_DIR / image_path.stem
    dbg_dir.mkdir(parents=True, exist_ok=True)
    if DESKEW:
        cv2.imwrite(str(dbg_dir / "deskew.png"), img)

    if layout == "row":
        debug = _crop_row_layout(img, image_path, row_candidate, csv_rows, global_state)
        cv2.imwrite(str(dbg_dir / "cells_row.png"), debug)
        print(
            f"Done: {image_path.name} -> layout=row "
            f"({len(row_candidate.bands)} rows x {row_candidate.num_cols} cols, "
            f"gap_cv={row_candidate.gap_cv:.3f}, "
            f"uniform_gap_ratio={row_candidate.gap_close_ratio:.3f})"
        )
        return

    debug = _crop_col_layout(img, image_path, col_candidate, csv_rows, global_state)
    cv2.imwrite(str(dbg_dir / "cells_col.png"), debug)
    print(
        f"Done: {image_path.name} -> layout=col "
        f"({len(col_candidate.row_bands)} rows x {len(col_candidate.answer_bands)} cols, "
        f"answer_bands={len(col_candidate.answer_bands)}, "
        f"row_gap_cv={row_candidate.gap_cv:.3f}, "
        f"row_uniform_gap_ratio={row_candidate.gap_close_ratio:.3f})"
    )


def _render_pdf_pages(pdf_path, rendered_dir):
    import fitz

    rendered_dir.mkdir(parents=True, exist_ok=True)
    rendered_paths = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(doc):
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(PDF_RENDER_ZOOM, PDF_RENDER_ZOOM),
                alpha=False,
            )
            out_path = rendered_dir / f"{pdf_path.stem}_pg_{page_index + 1:03d}.png"
            pixmap.save(str(out_path))
            rendered_paths.append(out_path)
    finally:
        doc.close()

    if not rendered_paths:
        raise ValueError(f"PDF has no pages: {pdf_path.name}")
    print(f"Rendered {len(rendered_paths)} page(s) from {pdf_path.name}")
    return rendered_paths


def _collect_input_pages():
    input_pages = []
    for ext in (".png", ".jpg", ".jpeg"):
        input_pages.extend(sorted(INPUT_DIR.glob(f"*{ext}")))

    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if pdfs:
        if RENDERED_INPUT_DIR.exists():
            shutil.rmtree(RENDERED_INPUT_DIR, ignore_errors=True)
        for pdf_path in pdfs:
            input_pages.extend(_render_pdf_pages(pdf_path, RENDERED_INPUT_DIR))

    return sorted(input_pages, key=lambda path: path.name.lower())


def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    if CLEAR_OUTPUT and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    images = _collect_input_pages()

    if not images:
        print("No image or PDF inputs found in:", INPUT_DIR)
        return

    csv_rows = [["layout", "page", "row", "col", "question", "path"]]
    global_state = {"current": GLOBAL_START}

    for img_path in images:
        process_image(img_path, csv_rows, global_state)

    csv_path = OUTPUT_DIR / "labels.csv"
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows(csv_rows)
        print("Saved labels:", csv_path)
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        alt_path = OUTPUT_DIR / f"labels_{ts}.csv"
        with alt_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows(csv_rows)
        print("labels.csv was locked; saved labels to:", alt_path)


if __name__ == "__main__":
    main()
