import csv
import os
import subprocess
from pathlib import Path

import cv2
import torch
from flask import Flask, request, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

from recognize_number import recognize_number, recognize_numbers


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


# ---------------- LOAD OCR MODEL ----------------

MODEL_DIR = "D:/best_model_v2"
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
    predicted = str(predicted).strip()
    correct_answer = str(correct_answer).strip()

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


# ---------------- ROUTE ----------------

@app.route("/process", methods=["POST"])
def process():
    try:
        # Clear input folder
        for f in INPUT_DIR.glob("*"):
            f.unlink()

        image_file = request.files.get("answer_sheet")
        answer_key_file = request.files.get("answer_key")

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

        # Run cropping
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

        return {
            "results": results,
            "total_correct": total_correct,
            "total_questions": total_q,
            "accuracy": accuracy,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
