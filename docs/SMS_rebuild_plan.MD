# SMS Rebuild — Consolidated Plan

Derived from SRS v1.0 (Parts 1–4). This is the reference document for the rebuild — schema,
requirements checklist, permission matrix, corrections vs. the old codebase, and build order.

---

## 1. Corrections vs. the Old Codebase

These are places where the old implementation diverged from the actual SRS. Fixing them is
part of the rebuild, not optional polish.

| # | Issue | Old behavior | Required behavior (SRS) |
|---|---|---|---|
| 1 | Student attendance edit rights | Super Admin could submit/edit student attendance | **Only Class Incharge** edits/submits. Super Admin/Principal are **view-only** (can unlock, not edit directly) — permission matrix, §9 |
| 2 | Teacher attendance edit rights | Super Admin and Principal both freely marked it | **Principal marks it.** Super Admin may submit **only if Principal hasn't** (BR-9). Once submitted, Super Admin is view/report only unless unlocked |
| 3 | Locked attendance enforcement | `ON CONFLICT DO UPDATE` didn't check `locked` before overwriting | Locked records must be **rejected at the service layer**, not silently overwritten (BR-7, §6.4) |
| 4 | Promotion | Manual promote-anyone, no pass/fail check | Should factor in exam pass/fail eligibility ("promote eligible, retain failed" — FR-13), while still allowing manual override by Super Admin/Principal |
| 5 | Reports | 4 report types delivered | SRS requires ~13 report types across Student/Teacher/Fee/School categories (FR-15), each with View + PDF + Print |
| 6 | Audit log FK | `user_id` could be the literal string `"system"` (not a real FK) | §6.4: "every audit log entry shall reference a valid system user" → need a real seeded **System** user row |
| 7 | Audit log categories | Ad hoc modules | Must explicitly cover Permission Changes and Principal Changes as categories (FR-16) |
| 8 | User privilege management | No real UI beyond toggling `is_class_incharge` | FR-18 requires Super Admin to manage **User Privileges** as a first-class settings function |
| 9 | Attendance unlock record | Reason + date + who, timestamp combined | Spec explicitly separates **Date, Time, User** as distinct captured fields (FR-9.3) — keep as separate columns, not just a combined timestamp string |

---

## 2. Roles & Permission Matrix (from SRS §9, authoritative)

| Module | Super Admin | Principal | Teacher | Class Incharge | Parent |
|---|---|---|---|---|---|
| Dashboard | ✔ | ✔ | ✔ | ✔ | ✔ |
| Student Management | ✔ | View | View | Assigned class only | Own child only |
| Parent Management | ✔ | View | ✘ | ✘ | Own profile |
| Teacher Management | ✔ | View | ✘ | ✘ | ✘ |
| Class Management | ✔ | View | ✘ | ✘ | ✘ |
| Subject Management | ✔ | View | View | View | ✘ |
| Teacher Assignment | ✔ | View | ✘ | ✘ | ✘ |
| Student Attendance | View + Unlock | View | ✘ | ✔ Edit | View |
| Teacher Attendance | View (Edit if Principal hasn't) | ✔ Edit | View own | View | ✘ |
| Attendance Unlock | ✔ | ✘ | ✘ | ✘ | ✘ |
| Examination | ✔ | View | ✔ | ✔ | View |
| Results | ✔ | View | ✔ | ✔ | View |
| Fee Management | ✔ | View | ✘ | ✘ | View |
| Reports | ✔ | ✔ | Limited | Limited | Own only |
| Audit Log | ✔ | Limited* | ✘ | ✘ | ✘ |
| Database Backup | ✔ | ✘ | ✘ | ✘ | ✘ |
| System Settings | ✔ | ✘ | ✘ | ✘ | ✘ |

\* Principal audit-log access is optional/configurable by Super Admin. **Default: restricted to Super Admin only** in v1; revisit if you want a toggle.

---

## 3. Business Rules Checklist (BR-1 → BR-13)

- [ ] Setup wizard runs exactly once, permanently disabled after
- [ ] Only Super Admin edits school settings post-setup
- [ ] Every student → exactly one class + one section
- [ ] Every student → exactly one linked parent
- [ ] Parent sees only their own child's records
- [ ] Attendance recorded once per day (unique per student/teacher per date)
- [ ] Attendance locks immediately on submission
- [ ] Only Super Admin unlocks attendance; reason mandatory
- [ ] Teacher attendance: Principal marks; Super Admin only if Principal hasn't
- [ ] Fee challans auto-generate monthly from the class fee structure
- [ ] Manual charges addable to any student's challan
- [ ] Every critical admin action → audit log entry
- [ ] Only Super Admin creates DB backups

---

## 4. Database Schema (proposed, SQLite)

```sql
-- Single-row school profile (id fixed = 1)
CREATE TABLE school (
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

-- Login accounts (Super Admin, Principal, Teacher, Class Incharge; NOT parents)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('super_admin','principal','teacher','class_incharge','system')),
    status TEXT DEFAULT 'active',           -- active | disabled
    display_name TEXT,
    created_at TEXT NOT NULL
);
-- Seed one immutable row: id='usr_system', role='system' — satisfies audit_log FK
-- for system-generated actions (seed data, automated jobs).

CREATE TABLE teachers (
    id TEXT PRIMARY KEY,
    employee_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    qualification TEXT,
    joining_date TEXT,
    employment_status TEXT DEFAULT 'active',
    is_class_incharge INTEGER DEFAULT 0,
    class_id TEXT REFERENCES classes(id),    -- set only if is_class_incharge=1
    user_id TEXT REFERENCES users(id) NOT NULL
);

CREATE TABLE parents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cnic TEXT UNIQUE NOT NULL,
    phone TEXT,
    address TEXT
);

CREATE TABLE classes (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE sections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class_id TEXT NOT NULL REFERENCES classes(id),
    UNIQUE(class_id, name)
    -- app layer enforces max 3 sections per class
);

CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE teacher_assignments (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id),
    class_id TEXT NOT NULL REFERENCES classes(id),
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    UNIQUE(teacher_id, class_id, subject_id)
);

CREATE TABLE students (
    id TEXT PRIMARY KEY,
    admission_id TEXT UNIQUE NOT NULL,
    roll_number TEXT UNIQUE NOT NULL,        -- global unique: needed for parent login lookup
    name TEXT NOT NULL,
    gender TEXT,
    dob TEXT,
    admission_date TEXT,
    status TEXT DEFAULT 'active',            -- active | inactive
    class_id TEXT NOT NULL REFERENCES classes(id),
    section_id TEXT NOT NULL REFERENCES sections(id),
    parent_id TEXT NOT NULL REFERENCES parents(id)
);

CREATE TABLE student_attendance (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Present','Absent','Leave')),
    locked INTEGER DEFAULT 0,
    submitted_at TEXT,
    submitted_by TEXT REFERENCES users(id),
    UNIQUE(student_id, date)
);

CREATE TABLE teacher_attendance (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id),
    date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Present','Absent','Leave')),
    locked INTEGER DEFAULT 0,
    submitted_at TEXT,
    submitted_by TEXT REFERENCES users(id),
    UNIQUE(teacher_id, date)
);

-- FR-9.3: Date, Time and User captured as distinct fields
CREATE TABLE attendance_unlocks (
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

CREATE TABLE examinations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exam_date TEXT,
    class_id TEXT NOT NULL REFERENCES classes(id),
    section_id TEXT REFERENCES sections(id),
    created_by TEXT REFERENCES users(id)
);

CREATE TABLE results (
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

CREATE TABLE fee_structures (
    id TEXT PRIMARY KEY,
    class_id TEXT UNIQUE NOT NULL REFERENCES classes(id),
    admission_fee REAL DEFAULT 0,
    tuition_fee REAL DEFAULT 0,
    exam_fee REAL DEFAULT 0,
    custom_name TEXT,
    custom_fee REAL DEFAULT 0
);

CREATE TABLE fee_challans (
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

CREATE TABLE manual_fees (
    id TEXT PRIMARY KEY,
    challan_id TEXT NOT NULL REFERENCES fee_challans(id),
    charge_type TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL
);

CREATE TABLE promotions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id),
    from_class TEXT REFERENCES classes(id),
    to_class TEXT REFERENCES classes(id),
    academic_year TEXT NOT NULL,
    status TEXT NOT NULL,             -- Promoted | Retained
    promoted_by TEXT REFERENCES users(id),
    promoted_at TEXT NOT NULL
);

CREATE TABLE audit_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),   -- always a real user, incl. 'usr_system'
    user_name TEXT NOT NULL,
    role TEXT NOT NULL,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    description TEXT
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**Open decision — parent login:** Parents authenticate via CNIC + roll number, so `roll_number`
must be globally unique (not just unique per class) for the lookup to be unambiguous — reflected
above. Confirm this matches your expectation before we build the auth module.

---

## 5. Module Build Order

Each module ships complete (schema → API → tests → frontend page) before moving to the next.

1. **Foundation** — config, db schema/migrations, security (password hashing, sessions), audit helper, seeded System user
2. **Auth & Setup Wizard** — FR-1, FR-2, UC-1
3. **Dashboard** (per-role) — FR-3
4. **Student & Parent Management** — FR-4, FR-5, UC-2
5. **Teacher Management & Assignments** — FR-6, FR-8, UC-3
6. **Class & Section Management** — FR-7 (incl. max-3-sections rule)
7. **Attendance (Student + Teacher)** — FR-9, FR-10, UC-4, UC-5, incl. lock/unlock enforcement
8. **Examinations & Results** — FR-11, FR-12, UC-6
9. **Promotion** — FR-13
10. **Fee Management** — FR-14, UC-7
11. **Reports** (all ~13 types, View + PDF + Print) — FR-15
12. **Audit Log** — FR-16
13. **Database Backup** — FR-17, UC-8
14. **System Settings & User Privileges** — FR-18
15. **Frontend polish pass** — responsive check across all modules (§4.1, §2.4)
16. **Full test suite** — mirrors acceptance criteria in §12

---

## 6. Stack (as discussed)

- Backend: Python + FastAPI
- DB: SQLite (single-school, matches §2.5 constraint)
- Auth: proper hashing (bcrypt/passlib) + signed sessions (PyJWT or itsdangerous)
- PDF: reportlab
- Frontend: vanilla JS, split per-module instead of one file
- Tests: pytest, one file per module, integration tests over the real API
