# API Documentation

## REST Endpoints Specification

### Authentication
- `POST /api/auth/login`
- `POST /api/auth/register`

### Exam Sessions
- `POST /api/exams/session/start`
- `POST /api/exams/session/submit`
- `GET /api/exams/session/<session_id>`

### Monitoring & Telemetry
- `POST /api/monitoring/events`
- `GET /api/monitoring/events/<session_id>`

### Integrity & Reports
- `GET /api/reports/<session_id>`
- `POST /api/reports/generate`

### Evidence
- `GET /api/evidence/<event_id>`
- `POST /api/evidence/upload`
