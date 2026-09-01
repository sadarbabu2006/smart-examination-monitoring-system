# Milestone 1 Database Design

## `candidates`

`id` is the primary key. The table stores `full_name`, unique case-insensitive `email`, optional unique `username`, `password_hash`, optional `registration_photo_path`, `created_at`, and `account_status`. Passwords are never stored in plaintext.

## `exam_sessions`

`id` is the primary key and `candidate_id` is a required foreign key to `candidates.id`. It stores `exam_identifier`, `status`, `started_at`, `ended_at`, and `created_at`. Valid statuses are `scheduled`, `active`, `paused`, and `submitted`.

Foreign-key enforcement is enabled for every SQLite connection. The relationship prevents a session from referencing a non-existent candidate and prevents deleting a candidate who owns a session.
