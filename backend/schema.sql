-- ============================================================
-- Abacus Evaluation System — SQLite Schema
-- ============================================================

-- 1. Users (auth)
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. Students (linked to users)
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    contact     TEXT,
    level       TEXT,
    center      TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Answer Keys (stored per exam_id by admin/teacher)
CREATE TABLE IF NOT EXISTS answer_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id         TEXT UNIQUE NOT NULL,
    file_path       TEXT,
    key_data        TEXT NOT NULL,
    uploaded_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. Submissions (one per upload attempt)
CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    exam_id         TEXT NOT NULL,
    file_path       TEXT,
    submitted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_questions INTEGER DEFAULT 0,
    total_correct   INTEGER DEFAULT 0,
    accuracy        REAL DEFAULT 0
);

-- 5. Results (one row per question per submission)
CREATE TABLE IF NOT EXISTS results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id     INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    question_number   INTEGER NOT NULL,
    image_url         TEXT,
    correct_answer    TEXT,
    detected_answer   TEXT,
    manual_corrected_answer TEXT,
    remark            TEXT,
    confidence        TEXT,
    is_corrected      INTEGER DEFAULT 0,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
