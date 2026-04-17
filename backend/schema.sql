-- ============================================================
-- Abacus Evaluation System — PostgreSQL Schema
-- ============================================================

-- 1. Students
CREATE TABLE IF NOT EXISTS students (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    contact     VARCHAR(20),
    level       VARCHAR(100),
    center      VARCHAR(100),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 2. Submissions  (one per upload attempt)
CREATE TABLE IF NOT EXISTS submissions (
    id           SERIAL PRIMARY KEY,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    exam_id      VARCHAR(50) NOT NULL,          -- Question Paper Code entered on Upload page
    submitted_at TIMESTAMP DEFAULT NOW(),
    total_questions INTEGER DEFAULT 0,
    total_correct   INTEGER DEFAULT 0,
    accuracy        NUMERIC(5,2) DEFAULT 0
);

-- 3. Results  (one row per question per submission)
CREATE TABLE IF NOT EXISTS results (
    id                SERIAL PRIMARY KEY,
    submission_id     INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    question_number   INTEGER NOT NULL,
    image_url         TEXT,
    correct_answer    TEXT,
    detected_answer   TEXT,
    remark            VARCHAR(50),
    confidence        TEXT,                     -- stored as text to hold "Manually corrected" or numeric
    is_corrected      BOOLEAN DEFAULT FALSE,
    updated_at        TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Seed data — sample students
-- ============================================================
INSERT INTO students (name, contact, level, center) VALUES
  ('Rahul',  '9876543210', 'Advanced Level 1', 'Kochi Center'),
  ('Anjali', '9876543211', 'Intermediate',      'Kochi Center'),
  ('Kiran',  '9876543212', 'Beginner',          'Thrissur Center')
ON CONFLICT DO NOTHING;
