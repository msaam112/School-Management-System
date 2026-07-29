"""Database layer: connection helper + full schema (SRS §6)."""
import sqlite3
import os
from datetime import datetime, date

from app.config import DB_PATH, BACKUP_DIR, SYSTEM_USER_ID, SYSTEM_USER_EMAIL, SYSTEM_USER_NAME
from app.security import hash_password, random_password


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS school (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    logo TEXT,
    address TEXT,
    emis_code TEXT,
    contact_number TEXT,
    principal_name TEXT,
    established_year TEXT,
    motto TEXT,
    setup_done INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('super_admin','principal','teacher','class_incharge','system')),
    status TEXT DEFAULT 'active',
    display_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id TEXT PRIMARY KEY,
    employee_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    qualification TEXT,
    joining_date TEXT,
    employment_status TEXT DEFAULT 'active',
    is_class_incharge INTEGER DEFAULT 0,
    class_id TEXT REFERENCES classes(id),
    user_id TEXT NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS parents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cnic TEXT UNIQUE NOT NULL,
    phone TEXT,
    address TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class_id TEXT NOT NULL REFERENCES classes(id),
    UNIQUE(class_id, name)
);

CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS teacher_assignments (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id),
    class_id TEXT NOT NULL REFERENCES classes(id),
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    UNIQUE(teacher_id, class_id, subject_id)
);

CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    admission_id TEXT UNIQUE NOT NULL,
    roll_number TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    gender TEXT,
    dob TEXT,
    admission_date TEXT,
    status TEXT DEFAULT 'active',
    class_id TEXT NOT NULL REFERENCES classes(id),
    section_id TEXT NOT NULL REFERENCES sections(id),
    parent_id TEXT NOT NULL REFERENCES parents(id)
);

CREATE TABLE IF NOT EXISTS student_attendance (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Present','Absent','Leave')),
    locked INTEGER DEFAULT 0,
    submitted_at TEXT,
    submitted_by TEXT REFERENCES users(id),
    UNIQUE(student_id, date)
);

CREATE TABLE IF NOT EXISTS teacher_attendance (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id),
    date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Present','Absent','Leave')),
    locked INTEGER DEFAULT 0,
    submitted_at TEXT,
    submitted_by TEXT REFERENCES users(id),
    UNIQUE(teacher_id, date)
);

CREATE TABLE IF NOT EXISTS attendance_unlocks (
    id TEXT PRIMARY KEY,
    attendance_type TEXT NOT NULL CHECK (attendance_type IN ('student','teacher')),
    ref_date TEXT NOT NULL,
    class_id TEXT REFERENCES classes(id),
    section_id TEXT REFERENCES sections(id),
    reason TEXT NOT NULL,
    unlocked_by TEXT NOT NULL REFERENCES users(id),
    unlock_date TEXT NOT NULL,
    unlock_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS examinations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exam_date TEXT,
    class_id TEXT NOT NULL REFERENCES classes(id),
    section_id TEXT REFERENCES sections(id),
    created_by TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    exam_id TEXT NOT NULL REFERENCES examinations(id),
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    obtained REAL NOT NULL,
    total REAL NOT NULL DEFAULT 100,
    percentage REAL NOT NULL,
    grade TEXT NOT NULL,
    pass_fail TEXT NOT NULL CHECK (pass_fail IN ('Pass','Fail')),
    UNIQUE(student_id, exam_id, subject_id)
);

CREATE TABLE IF NOT EXISTS fee_structures (
    id TEXT PRIMARY KEY,
    class_id TEXT UNIQUE NOT NULL REFERENCES classes(id),
    admission_fee REAL DEFAULT 0,
    tuition_fee REAL DEFAULT 0,
    exam_fee REAL DEFAULT 0,
    custom_name TEXT,
    custom_fee REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fee_challans (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    total REAL DEFAULT 0,
    status TEXT DEFAULT 'Unpaid' CHECK (status IN ('Paid','Unpaid','Partially Paid')),
    UNIQUE(student_id, month, year)
);

CREATE TABLE IF NOT EXISTS manual_fees (
    id TEXT PRIMARY KEY,
    challan_id TEXT NOT NULL REFERENCES fee_challans(id),
    charge_type TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS promotions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    from_class TEXT REFERENCES classes(id),
    to_class TEXT REFERENCES classes(id),
    academic_year TEXT NOT NULL,
    status TEXT NOT NULL,
    promoted_by TEXT REFERENCES users(id),
    promoted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    user_name TEXT NOT NULL,
    role TEXT NOT NULL,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    # Seed the immutable System user (satisfies audit_log FK for automated actions).
    existing = conn.execute("SELECT id FROM users WHERE id=?", (SYSTEM_USER_ID,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, status, display_name, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (SYSTEM_USER_ID, SYSTEM_USER_EMAIL, hash_password(random_password(24)),
             "system", "active", SYSTEM_USER_NAME, now_iso()),
        )
        conn.commit()

    conn.close()
    os.makedirs(BACKUP_DIR, exist_ok=True)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def fetchone(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def fetchall(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()