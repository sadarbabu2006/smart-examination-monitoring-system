# Milestone 1 Architecture

The Flask application factory creates the SQLite schema, registers only the candidate authentication and exam-session blueprints, and exposes `/api/health`. SQLite access uses Python's built-in `sqlite3` with foreign keys enabled on every connection.

Candidates register with a securely hashed password and may capture one registration photo using the modular OpenCV helper. The photo is saved in `data/registration_photos` (or `REGISTRATION_PHOTO_DIR`) and its path is stored with the candidate.

After login, Flask's signed session cookie carries the candidate ID. All session routes compare that ID with the session owner. The lifecycle is `scheduled -> active -> paused -> active -> submitted`; only active sessions may be submitted.

`scripts/generate_synthetic_data.py` uses Faker to create non-production JSON session-log samples for later work. Monitoring, scoring, analytics, AI, reporting, and the dashboard are deliberately outside this milestone.
