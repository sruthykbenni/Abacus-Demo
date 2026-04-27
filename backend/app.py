import csv
import json
import os
import subprocess
from pathlib import Path

import bcrypt
import cv2
import sqlite3
import torch
from flask import Flask, jsonify, request, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

from recognize_number import normalize_numeric_text, recognize_number, recognize_numbers


# ---------------- CONFIG ----------------

BASE_DIR        = Path(__file__).resolve().parent
INPUT_DIR       = BASE_DIR / "input"
OUTPUT_DIR      = BASE_DIR / "output" / "boxes"
ANSWER_KEY_DIR  = BASE_DIR / "answer_keys"
RESULTS_DIR     = BASE_DIR / "results"
UPLOADS_DIR     = BASE_DIR / "uploads"          # answer sheet uploads

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
ALLOWED_PDF_EXTENSIONS   = {"pdf"}
MISSING_ANSWER           = "-"
OCR_CONFIDENCE_THRESHOLD = 0.60

INPUT_DIR.mkdir(exist_ok=True)
ANSWER_KEY_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
CORS(app)


# ---------------- DATABASE ----------------

DB_FILE = BASE_DIR / "abacus.db"


def get_db():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db_compat():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(results)")
    columns = {row["name"] for row in cur.fetchall()}

    if "manual_corrected_answer" not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN manual_corrected_answer TEXT")

    conn.commit()
    cur.close()
    conn.close()


ensure_db_compat()


# ---------------- LOAD OCR MODEL ----------------

MODEL_DIR  = BASE_DIR / "best_model_v2"
device     = torch.device("cuda" if torch.cuda.is_available() else "cpu")
OCR_BATCH_SIZE = 8 if device.type == "cuda" else 4

_ocr_model_cache     = None
_ocr_processor_cache = None


def get_ocr_model_and_processor():
    global _ocr_model_cache, _ocr_processor_cache
    if _ocr_model_cache is None or _ocr_processor_cache is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        print("Loading OCR model...")
        _ocr_processor_cache = TrOCRProcessor.from_pretrained(str(MODEL_DIR))
        _ocr_model_cache     = VisionEncoderDecoderModel.from_pretrained(str(MODEL_DIR)).to(device)
        _ocr_model_cache.eval()
        print("OCR model loaded")
    return _ocr_model_cache, _ocr_processor_cache


# ---------------- HELPERS ----------------

def allowed_file(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


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
            results.append({"question": int(row["question"]), "raw_path": row["path"]})
    return results


def load_answer_key_from_pdf(pdf_path):
    from extract_key import extract_answer_key
    return extract_answer_key(pdf_path)[1]


def get_effective_answer(result_row):
    if result_row["is_corrected"] and result_row["manual_corrected_answer"]:
        return normalize_numeric_text(result_row["manual_corrected_answer"])
    return normalize_numeric_text(result_row["detected_answer"])


def build_remark(predicted, confidence, correct_answer):
    predicted      = normalize_numeric_text(predicted)
    correct_answer = normalize_numeric_text(correct_answer)
    if "?" in predicted or predicted == "":
        return "Unable to read"
    if len(predicted) != len(correct_answer):
        return "Unable to read"
    if confidence < OCR_CONFIDENCE_THRESHOLD:
        return "Unable to read"
    if predicted == correct_answer:
        return "Correct"
    return "Wrong"


def evaluate_cropped_answers_batch(image_paths, correct_answers, model, processor):
    images       = []
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
            correct_str   = str(correct_answers[idx]).strip()
            remark        = build_remark(predicted_str, confidence, correct_str)
            results[idx]  = (remark, round(confidence * 100, 2), predicted_str)
    return results


def load_answer_key_for_exam(cur, exam_id):
    cur.execute("SELECT key_data FROM answer_keys WHERE exam_id = ?", (exam_id,))
    row = cur.fetchone()
    if not row:
        return {}
    return {
        int(k): normalize_numeric_text(v)
        for k, v in json.loads(row["key_data"]).items()
    }


def build_remark_from_stored_result(detected_answer, manual_corrected_answer, confidence, correct_answer, is_corrected):
    correct_answer = normalize_numeric_text(correct_answer)
    detected_answer = normalize_numeric_text(detected_answer)
    manual_corrected_answer = normalize_numeric_text(manual_corrected_answer)
    effective_answer = manual_corrected_answer if is_corrected and manual_corrected_answer else detected_answer

    if correct_answer == MISSING_ANSWER:
        return "Unable to read"

    if is_corrected:
        return "Correct" if effective_answer == correct_answer else "Wrong"

    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0

    return build_remark(detected_answer, confidence_value, correct_answer)


def backfill_submission_answer_key(conn, submission_id, exam_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS missing_count FROM results "
        "WHERE submission_id = ? AND (correct_answer IS NULL OR correct_answer = ?)",
        (submission_id, MISSING_ANSWER)
    )
    row = cur.fetchone()
    missing_count = row["missing_count"] if row else 0
    if not missing_count:
        cur.close()
        return False

    answer_key_dict = load_answer_key_for_exam(cur, exam_id)
    if not answer_key_dict:
        cur.close()
        return False

    cur.execute(
        "SELECT id, question_number, detected_answer, manual_corrected_answer, confidence, is_corrected "
        "FROM results WHERE submission_id = ? ORDER BY question_number",
        (submission_id,)
    )
    result_rows = cur.fetchall()

    total_q = 0
    total_correct = 0

    for result in result_rows:
        question = result["question_number"]
        correct_answer = answer_key_dict.get(question, MISSING_ANSWER)

        if correct_answer != MISSING_ANSWER:
            total_q += 1

        remark = build_remark_from_stored_result(
            result["detected_answer"],
            result["manual_corrected_answer"],
            result["confidence"],
            correct_answer,
            result["is_corrected"],
        )

        if correct_answer != MISSING_ANSWER and remark == "Correct":
            total_correct += 1

        cur.execute(
            "UPDATE results SET correct_answer = ?, remark = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (correct_answer, remark, result["id"])
        )

    accuracy = round((total_correct / total_q) * 100, 2) if total_q else 0
    cur.execute(
        "UPDATE submissions SET total_questions = ?, total_correct = ?, accuracy = ? WHERE id = ?",
        (total_q, total_correct, accuracy, submission_id)
    )
    conn.commit()
    cur.close()
    return True


# ================================================================
# AUTH ROUTES
# ================================================================

@app.route("/login", methods=["POST"])
def login():
    """Authenticate user and return role + ids."""
    data     = request.get_json()
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            return jsonify({"error": "Invalid credentials"}), 401

        # Verify password (bcrypt)
        if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
            return jsonify({"error": "Invalid credentials"}), 401

        response = {
            "user_id":  user["id"],
            "username": user["username"],
            "role":     user["role"],
        }

        # If student, also return student record id
        if user["role"] == "student":
            conn = get_db()
            cur  = conn.cursor()
            cur.execute("SELECT id FROM students WHERE user_id = ?", (user["id"],))
            student = cur.fetchone()
            cur.close()
            conn.close()
            response["student_id"] = student["id"] if student else None

        return jsonify(response)

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/register", methods=["POST"])
def register():
    """Register a new user (admin/teacher only in production)."""
    data     = request.get_json()
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "")
    role     = (data or {}).get("role", "student")
    name     = (data or {}).get("name", username)

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if role not in ("student", "teacher", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
        user_id = cur.lastrowid

        if role == "student":
            cur.execute(
                "INSERT INTO students (user_id, name) VALUES (?, ?)",
                (user_id, name)
            )
            student_id = cur.lastrowid
        else:
            student_id = None

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"user_id": user_id, "student_id": student_id, "role": role}), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# ANSWER KEY ROUTES (Admin / Teacher)
# ================================================================

@app.route("/answer-keys", methods=["POST"])
def upload_answer_key():
    """
    Upload and store an answer key PDF for a given exam_id.
    Form fields: exam_id (text), answer_key (file), uploaded_by (user_id)
    """
    exam_id     = request.form.get("exam_id", "").strip()
    uploaded_by = request.form.get("uploaded_by")
    key_file    = request.files.get("answer_key")

    if not exam_id:
        return jsonify({"error": "exam_id is required"}), 400
    if not key_file:
        return jsonify({"error": "answer_key PDF is required"}), 400
    if not allowed_file(key_file.filename, ALLOWED_PDF_EXTENSIONS):
        return jsonify({"error": "Only PDF files allowed for answer key"}), 400

    try:
        # Save PDF to answer_keys folder
        safe_name = secure_filename(key_file.filename)
        pdf_path  = ANSWER_KEY_DIR / f"{exam_id}_{safe_name}"
        key_file.save(pdf_path)

        # Extract key data using existing ML logic
        from extract_key import extract_answer_key
        all_pages = extract_answer_key(str(pdf_path))
        # Merge all pages into one flat dict {question_number: answer}
        key_data = {}
        for page_dict in all_pages.values():
            key_data.update(page_dict)

        if not key_data:
            return jsonify({"error": "Could not extract answers from PDF"}), 422

        # Persist to DB (upsert)
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO answer_keys (exam_id, file_path, key_data, uploaded_by, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (exam_id, str(pdf_path), json.dumps(key_data), uploaded_by)
        )
        key_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message":         "Answer key stored",
            "key_id":          key_id,
            "exam_id":         exam_id,
            "question_count":  len(key_data),
            "preview":         dict(list(key_data.items())[:5]),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/answer-keys", methods=["GET"])
def list_answer_keys():
    """List all stored answer keys."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT ak.id, ak.exam_id, ak.key_data, ak.created_at, ak.updated_at, u.username AS uploaded_by "
            "FROM answer_keys ak "
            "LEFT JOIN users u ON u.id = ak.uploaded_by "
            "ORDER BY ak.created_at DESC"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        result = []
        for row in rows:
            row_dict = dict(row)
            key_data = json.loads(row_dict["key_data"] or "{}")
            row_dict["question_count"] = len(key_data)
            row_dict.pop("key_data", None)
            result.append(row_dict)

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/answer-keys/<exam_id>", methods=["GET"])
def get_answer_key(exam_id):
    """Retrieve stored answer key by exam_id."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, exam_id, key_data, created_at FROM answer_keys WHERE exam_id = ?",
            (exam_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({"error": "Answer key not found for this exam_id"}), 404
        data = dict(row)
        data["key_data"] = json.loads(data["key_data"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/answer-keys/<exam_id>", methods=["DELETE"])
def delete_answer_key(exam_id):
    """Delete an answer key by exam_id."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("DELETE FROM answer_keys WHERE exam_id = ?", (exam_id,))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if deleted == 0:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"message": f"Answer key for {exam_id} deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ================================================================
# MAIN PROCESS ROUTE (Student Upload)
# ================================================================

@app.route("/process", methods=["POST"])
def process():
    try:
        # Clear input folder
        for f in INPUT_DIR.glob("*"):
            f.unlink()

        image_file      = request.files.get("answer_sheet")
        answer_key_file = request.files.get("answer_key")   # optional fallback
        student_id      = request.form.get("student_id")
        exam_id         = request.form.get("exam_id", "").strip()

        if not image_file:
            return jsonify({"error": "No answer sheet uploaded"}), 400
        if not exam_id:
            return jsonify({"error": "exam_id is required"}), 400

        # Save uploaded answer sheet
        safe_name  = secure_filename(image_file.filename)
        image_path = INPUT_DIR / safe_name
        image_file.save(image_path)

        # ── Save copy to uploads dir for record ──
        stored_path = None
        if student_id:
            stored_path = UPLOADS_DIR / f"student_{student_id}_{exam_id}_{safe_name}"
            import shutil
            shutil.copy(image_path, stored_path)

        # ── Resolve answer key ──
        # Priority: 1) DB lookup by exam_id  2) uploaded PDF  3) empty
        answer_key_dict = {}

        try:
            conn = get_db()
            cur  = conn.cursor()
            cur.execute("SELECT key_data FROM answer_keys WHERE exam_id = ?", (exam_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                answer_key_dict = {int(k): v for k, v in json.loads(row["key_data"]).items()}
            elif answer_key_file:
                pdf_path = ANSWER_KEY_DIR / secure_filename(answer_key_file.filename)
                answer_key_file.save(pdf_path)
                answer_key_dict = load_answer_key_from_pdf(pdf_path)
        except Exception as key_err:
            import traceback; traceback.print_exc()
            print(f"[KEY WARNING] Could not load answer key: {key_err}")

        # ── Run cropping (untouched) ──
        run_cropping_script()
        cropped_data = load_labels()

        results      = []
        total_q      = 0
        total_correct = 0

        model, processor = get_ocr_model_and_processor()

        for i in range(0, len(cropped_data), OCR_BATCH_SIZE):
            batch   = cropped_data[i:i + OCR_BATCH_SIZE]
            paths   = [Path(x["raw_path"]) for x in batch]
            answers = [answer_key_dict.get(x["question"], MISSING_ANSWER) for x in batch]

            batch_results = evaluate_cropped_answers_batch(paths, answers, model, processor)

            for item, res in zip(batch, batch_results):
                remark, confidence, predicted = res
                correct = answer_key_dict.get(item["question"], MISSING_ANSWER)

                if correct != MISSING_ANSWER:
                    total_q += 1
                    if remark == "Correct":
                        total_correct += 1

                results.append({
                    "question":        item["question"],
                    "image_url":       url_for(
                        "serve_output",
                        filename=Path(item["raw_path"]).relative_to(OUTPUT_DIR).as_posix()
                    ),
                    "correct_answer":  correct,
                    "detected_answer": predicted,
                    "remark":          remark,
                    "confidence":      confidence,
                })

        accuracy = round((total_correct / total_q) * 100, 2) if total_q else 0

        # ── Persist to DB ──
        submission_id = None
        if student_id:
            try:
                conn = get_db()
                cur  = conn.cursor()

                cur.execute(
                    "INSERT INTO submissions (student_id, exam_id, file_path, total_questions, total_correct, accuracy) VALUES (?, ?, ?, ?, ?, ?)",
                    (int(student_id), exam_id, str(stored_path) if stored_path else None,
                     total_q, total_correct, accuracy)
                )
                submission_id = cur.lastrowid

                for r in results:
                    cur.execute(
                        "INSERT INTO results (submission_id, question_number, image_url, correct_answer, detected_answer, manual_corrected_answer, remark, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (submission_id, r["question"], r["image_url"],
                         r["correct_answer"], r["detected_answer"], None,
                         r["remark"], str(r["confidence"]))
                    )

                conn.commit()
                cur.close()
                conn.close()
            except Exception as db_err:
                import traceback; traceback.print_exc()
                print(f"[DB WARNING] Could not persist results: {db_err}")

        return jsonify({
            "results":          results,
            "total_correct":    total_correct,
            "total_questions":  total_q,
            "accuracy":         accuracy,
            "submission_id":    submission_id,
            "answer_key_found": bool(answer_key_dict),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)


# ================================================================
# STUDENT ROUTES
# ================================================================

@app.route("/students", methods=["GET"])
def get_students():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id, name, contact, level, center FROM students ORDER BY id")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/students/<int:student_id>", methods=["GET"])
def get_student(student_id):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, name, contact, level, center FROM students WHERE id = ?",
            (student_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({"error": "Student not found"}), 404
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/students/<int:student_id>/submissions", methods=["GET"])
def get_student_submissions(student_id):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id AS submission_id, exam_id, submitted_at AS date, total_questions, total_correct, accuracy "
            "FROM submissions WHERE student_id = ? ORDER BY submitted_at DESC",
            (student_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ================================================================
# SUBMISSION ROUTES
# ================================================================

@app.route("/submissions/<int:submission_id>", methods=["GET"])
def get_submission(submission_id):
    try:
        conn = get_db()
        cur  = conn.cursor()

        cur.execute(
            "SELECT id, student_id, exam_id, submitted_at AS date, total_questions, total_correct, accuracy "
            "FROM submissions WHERE id = ?",
            (submission_id,)
        )
        sub = cur.fetchone()
        if not sub:
            cur.close()
            conn.close()
            return jsonify({"error": "Submission not found"}), 404

        cur.close()
        backfill_submission_answer_key(conn, submission_id, sub["exam_id"])

        cur = conn.cursor()
        cur.execute(
            "SELECT id, student_id, exam_id, submitted_at AS date, total_questions, total_correct, accuracy "
            "FROM submissions WHERE id = ?",
            (submission_id,)
        )
        sub = cur.fetchone()

        cur.execute(
            "SELECT question_number AS question, image_url, correct_answer, detected_answer, manual_corrected_answer, remark, confidence, is_corrected "
            "FROM results WHERE submission_id = ? ORDER BY question_number",
            (submission_id,)
        )
        result_rows = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify({
            "submission": dict(sub),
            "results":    [dict(r) for r in result_rows],
            "summary": {
                "total_questions": sub["total_questions"],
                "total_correct":   sub["total_correct"],
                "accuracy":        float(sub["accuracy"]),
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/submissions/<int:submission_id>/results", methods=["PATCH"])
def update_results(submission_id):
    try:
        data        = request.get_json()
        corrections = data.get("corrections", [])

        if not corrections:
            return jsonify({"error": "No corrections provided"}), 400

        conn = get_db()
        cur  = conn.cursor()

        for c in corrections:
            cur.execute(
                "SELECT detected_answer, correct_answer FROM results WHERE submission_id = ? AND question_number = ?",
                (submission_id, c["question"])
            )
            existing = cur.fetchone()
            if not existing:
                continue

            corrected_answer = normalize_numeric_text(c["manual_corrected_answer"])
            correct_answer = normalize_numeric_text(existing["correct_answer"])
            remark = "Correct" if corrected_answer == correct_answer else "Wrong"

            cur.execute(
                "UPDATE results SET manual_corrected_answer = ?, remark = ?, is_corrected = 1, updated_at = CURRENT_TIMESTAMP WHERE submission_id = ? AND question_number = ?",
                (corrected_answer, remark, submission_id, c["question"])
            )

        cur.execute(
            "SELECT COUNT(*) AS total_questions, SUM(CASE WHEN remark = 'Correct' THEN 1 ELSE 0 END) AS total_correct "
            "FROM results WHERE submission_id = ? AND correct_answer != ?",
            (submission_id, MISSING_ANSWER)
        )
        row = cur.fetchone()
        total_q, total_correct = row
        accuracy = round((total_correct / total_q) * 100, 2) if total_q else 0

        cur.execute(
            "UPDATE submissions SET total_questions = ?, total_correct = ?, accuracy = ? WHERE id = ?",
            (total_q, total_correct, accuracy, submission_id)
        )

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message":         "Corrections saved",
            "total_questions": total_q,
            "total_correct":   total_correct,
            "accuracy":        accuracy,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ================================================================
# TEACHER: EXAM SUMMARY
# ================================================================

@app.route("/exams/<exam_id>/submissions", methods=["GET"])
def get_exam_submissions(exam_id):
    """All submissions for a particular exam across all students."""
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT s.id AS submission_id, s.submitted_at AS date, s.total_questions, s.total_correct, s.accuracy, st.id AS student_id, st.name AS student_name "
            "FROM submissions s JOIN students st ON st.id = s.student_id WHERE s.exam_id = ? ORDER BY s.submitted_at DESC",
            (exam_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
