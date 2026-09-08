-- Milestone 1 & 2 schema.
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    username TEXT UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    registration_photo_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active', 'inactive'))
);

CREATE TABLE IF NOT EXISTS exam_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    exam_identifier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'active', 'paused', 'submitted')),
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_exam_sessions_candidate_id ON exam_sessions(candidate_id);

CREATE TABLE IF NOT EXISTS monitoring_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details TEXT,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_monitoring_events_session_id ON monitoring_events(session_id);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_type ON monitoring_events(event_type);

CREATE TABLE IF NOT EXISTS face_absence_intervals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_face_absence_session_id ON face_absence_intervals(session_id);

CREATE TABLE IF NOT EXISTS integrity_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE,
    integrity_score INTEGER NOT NULL CHECK (integrity_score >= 0 AND integrity_score <= 100),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    face_presence_ratio REAL,
    monitored_duration_seconds REAL,
    face_absence_seconds REAL,
    suspicious_event_count INTEGER NOT NULL DEFAULT 0,
    breakdown TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_integrity_scores_session_id ON integrity_scores(session_id);

CREATE TABLE IF NOT EXISTS proctor_admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('PROCTOR', 'ADMIN')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_proctor_admins_email ON proctor_admins(email);

