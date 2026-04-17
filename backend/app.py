import csv
import os
import subprocess
from pathlib import Path

import cv2
import psycopg2
import psycopg2.extras
import torch
from flask import Flask, jsonify, request, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

from recognize_number import normalize_numeric_text, recognize_number, recognize_numbers


# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output" / "boxes"
ANSWER_KEY_DIR = BASE_DIR / "answer_keys"
RESULTS_DIR = BASE_DIR / "results"

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
ALLOWED_PDF_EXTENSIONS = {"pdf"}
MISSING_ANSWER = "-"
OCR_CONFIDENCE_THRESHOLD = 0.60  # Calibrated on current handwritten answer-sheet samples.

INPUT_DIR.mkdir(exist_ok=True)
ANSWER_KEY_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
CORS(app)


# ---------------- DATABASE ----------------

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "abacus_db"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "root"),
}


def get_db():
    """Return a new psycopg2 connection (caller must close it)."""
    return psycopg2.connect(**DB_CONFIG)


# ---------------- LOAD OCR MODEL ----------------

MODEL_DIR = BASE_DIR / "best_model_v2"
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

OCR_BATCH_SIZE = 8 if device.type == "cuda" else 4

_ocr_model_cache = None
_ocr_processor_cache = None


def get_ocr_model_and_processor():
    global _ocr_model_cache, _ocr_processor_cache

    if _ocr_model_cache is None or _ocr_processor_cache is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        print("Loading OCR model...")

        _ocr_processor_cache = TrOCRProcessor.from_pretrained(str(MODEL_DIR))
        _ocr_model_cache = VisionEncoderDecoderModel.from_pretrained(str(MODEL_DIR)).to(device)
        _ocr_model_cache.eval()

        print("OCR model loaded")

    return _ocr_model_cache, _ocr_processor_cache


# ---------------- HELPERS ----------------

def allowed_file(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


# ✅ FIXED CROPPING CALL (IMPORTANT)
def run_cropping_script():
    subprocess.run(
        ["python", "extract_answer_boxes-auto.py"],
        cwd=BASE_DIR,
        check=True
    )


def load_labels():
    labels_path = OUTPUT_DIR / "labels.csv"
    results = []

    if not labels_path.exists():
        return results

    with labels_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(
                {
                    "question": int(row["question"]),
                    "raw_path": row["path"],
                }
            )

    return results


def load_answer_key(pdf_path):
    from extract_key import extract_answer_key
    return extract_answer_key(pdf_path)[1]


def build_remark(predicted, confidence, correct_answer):
    predicted = normalize_numeric_text(predicted)
    correct_answer = normalize_numeric_text(correct_answer)

    # ❌ Missing / unreadable digits
    if "?" in predicted or predicted == "":
        return "Unable to read"

    # ❌ Length mismatch (VERY IMPORTANT FIX)
    if len(predicted) != len(correct_answer):
        return "Unable to read"

    # ❌ Low confidence (new stricter check)
    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return "Unable to read"

    # ✅ Correct match
    if predicted == correct_answer:
        return "Correct"

    # ❌ Wrong but confident
    return "Wrong"


def evaluate_cropped_answers_batch(image_paths, correct_answers, model, processor):
    images = []
    valid_indices = []

    for i, path in enumerate(image_paths):
        img = cv2.imread(str(path))
        if img is not None:
            images.append(img)
            valid_indices.append(i)

    results = [("Unable to read", 0.0, "")] * len(image_paths)

    if images:
        preds = recognize_numbers(images, model, processor, device)

        for idx, (predicted, confidence) in zip(valid_indices, preds):
            predicted_str = str(predicted).strip()
            correct_str = str(correct_answers[idx]).strip()

            remark = build_remark(
                predicted_str,
                confidence,
                correct_str
            )

            results[idx] = (
                remark,
                round(confidence * 100, 2),
                predicted_str
            )

    return results


# ================================================================
# EXISTING ROUTE — only DB persistence added at the end
# ================================================================

@app.route("/process", methods=["POST"])
def process():
    try:
        # Clear input folder
        for f in INPUT_DIR.glob("*"):
            f.unlink()

        image_file = request.files.get("answer_sheet")
        answer_key_file = request.files.get("answer_key")

        # ── NEW: read student_id and exam_id from form ──
        student_id = request.form.get("student_id")
        exam_id    = request.form.get("exam_id", "UNKNOWN")

        if not image_file:
            return {"error": "No answer sheet uploaded"}, 400

        # Save image
        image_path = INPUT_DIR / secure_filename(image_file.filename)
        image_file.save(image_path)

        # Load answer key
        answer_key_dict = {}
        if answer_key_file:
            pdf_path = ANSWER_KEY_DIR / secure_filename(answer_key_file.filename)
            answer_key_file.save(pdf_path)
            answer_key_dict = load_answer_key(pdf_path)

        # Run cropping  ← UNTOUCHED
        run_cropping_script()

        cropped_data = load_labels()

        results = []
        total_q = 0
        total_correct = 0

        model, processor = get_ocr_model_and_processor()

        for i in range(0, len(cropped_data), OCR_BATCH_SIZE):
            batch = cropped_data[i:i+OCR_BATCH_SIZE]

            paths = [Path(x["raw_path"]) for x in batch]
            answers = [
                answer_key_dict.get(x["question"], MISSING_ANSWER)
                for x in batch
            ]

            batch_results = evaluate_cropped_answers_batch(
                paths, answers, model, processor
            )

            for item, res in zip(batch, batch_results):
                remark, confidence, predicted = res

                correct = answer_key_dict.get(item["question"], MISSING_ANSWER)

                if correct != MISSING_ANSWER:
                    total_q += 1
                    if remark == "Correct":
                        total_correct += 1

                results.append({
                    "question": item["question"],
                    "image_url": url_for(
                        "serve_output",
                        filename=Path(item["raw_path"]).relative_to(OUTPUT_DIR).as_posix()
                    ),
                    "correct_answer": correct,
                    "detected_answer": predicted,
                    "remark": remark,
                    "confidence": confidence,
                })

        accuracy = round((total_correct / total_q) * 100, 2) if total_q else 0

        # ── NEW: persist to DB ──
        submission_id = None
        if student_id:
            try:
                conn = get_db()
                cur  = conn.cursor()

                # Insert submission
                cur.execute(
                    """
                    INSERT INTO submissions
                        (student_id, exam_id, total_questions, total_correct, accuracy)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (int(student_id), exam_id, total_q, total_correct, accuracy)
                )
                submission_id = cur.fetchone()[0]

                # Insert per-question results
                for r in results:
                    cur.execute(
                        """
                        INSERT INTO results
                            (submission_id, question_number, image_url,
                             correct_answer, detected_answer, remark, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            submission_id,
                            r["question"],
                            r["image_url"],
                            r["correct_answer"],
                            r["detected_answer"],
                            r["remark"],
                            str(r["confidence"]),
                        )
                    )

                conn.commit()
                cur.close()
                conn.close()
            except Exception as db_err:
                import traceback
                traceback.print_exc()
                print(f"[DB WARNING] Could not persist results: {db_err}")
                # Do NOT fail the request — evaluation still works without DB

        return {
            "results":          results,
            "total_correct":    total_correct,
            "total_questions":  total_q,
            "accuracy":         accuracy,
            "submission_id":    submission_id,   # frontend uses this for navigation
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)


# ================================================================
# NEW ROUTES — DB-backed APIs
# ================================================================

@app.route("/students", methods=["GET"])
def get_students():
    """Return all students for the session page."""
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, name, contact, level, center FROM students ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/students/<int:student_id>", methods=["GET"])
def get_student(student_id):
    """Return a single student's profile."""
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, name, contact, level, center FROM students WHERE id = %s",
            (student_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"error": "Student not found"}, 404
        return jsonify(dict(row))
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/students/<int:student_id>/submissions", methods=["GET"])
def get_student_submissions(student_id):
    """Return all submissions for a student (for the report page)."""
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT id AS submission_id, exam_id, submitted_at::date AS date,
                   total_questions, total_correct, accuracy
            FROM submissions
            WHERE student_id = %s
            ORDER BY submitted_at DESC
            """,
            (student_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/submissions/<int:submission_id>", methods=["GET"])
def get_submission(submission_id):
    """Return full results for a single submission (for evaluation page load from DB)."""
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Summary
        cur.execute(
            """
            SELECT id, student_id, exam_id, submitted_at::date AS date,
                   total_questions, total_correct, accuracy
            FROM submissions WHERE id = %s
            """,
            (submission_id,)
        )
        sub = cur.fetchone()
        if not sub:
            cur.close()
            conn.close()
            return {"error": "Submission not found"}, 404

        # Results
        cur.execute(
            """
            SELECT question_number AS question, image_url, correct_answer,
                   detected_answer, remark, confidence, is_corrected
            FROM results
            WHERE submission_id = %s
            ORDER BY question_number
            """,
            (submission_id,)
        )
        result_rows = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify({
            "submission": dict(sub),
            "results": [dict(r) for r in result_rows],
            "summary": {
                "total_questions": sub["total_questions"],
                "total_correct":   sub["total_correct"],
                "accuracy":        float(sub["accuracy"]),
            }
        })
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/submissions/<int:submission_id>/results", methods=["PATCH"])
def update_results(submission_id):
    """
    Save manual corrections for one or more questions.
    Body: { "corrections": [ { "question": 3, "detected_answer": "42", "remark": "Correct" }, ... ] }
    Also recalculates and updates the submission summary.
    """
    try:
        data        = request.get_json()
        corrections = data.get("corrections", [])

        if not corrections:
            return {"error": "No corrections provided"}, 400

        conn = get_db()
        cur  = conn.cursor()

        for c in corrections:
            cur.execute(
                """
                UPDATE results
                SET detected_answer = %s,
                    remark          = %s,
                    confidence      = 'Manually corrected',
                    is_corrected    = TRUE,
                    updated_at      = NOW()
                WHERE submission_id = %s AND question_number = %s
                """,
                (c["detected_answer"], c["remark"], submission_id, c["question"])
            )

        # Recalculate summary
        cur.execute(
            """
            SELECT
                COUNT(*)                                        AS total_questions,
                COUNT(*) FILTER (WHERE remark = 'Correct')     AS total_correct
            FROM results
            WHERE submission_id = %s
              AND correct_answer != %s
            """,
            (submission_id, MISSING_ANSWER)
        )
        row = cur.fetchone()
        total_q, total_correct = row
        accuracy = round((total_correct / total_q) * 100, 2) if total_q else 0

        cur.execute(
            """
            UPDATE submissions
            SET total_questions = %s,
                total_correct   = %s,
                accuracy        = %s
            WHERE id = %s
            """,
            (total_q, total_correct, accuracy, submission_id)
        )

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message":        "Corrections saved",
            "total_questions": total_q,
            "total_correct":   total_correct,
            "accuracy":        accuracy,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
