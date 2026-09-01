"""Generate non-production synthetic session-log records for future testing.

Example: ``python scripts/generate_synthetic_data.py --count 25 --seed 7``.
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "synthetic" / "session_logs.json"
BEHAVIOURS = ("normal", "interrupted", "review_required")


def generate_session_records(count=20, seed=None):
    """Return ``count`` reproducible fake candidate-session records when seeded."""
    if count < 1:
        raise ValueError("count must be at least 1")
    faker = Faker()
    rng = random.Random(seed)
    if seed is not None:
        faker.seed_instance(seed)
    anchor = datetime(2025, 1, 1, tzinfo=timezone.utc)
    records = []
    for index in range(count):
        behaviour = rng.choice(BEHAVIOURS)
        started_at = anchor + timedelta(days=rng.randint(0, 180), minutes=rng.randint(0, 1440))
        duration_minutes = rng.randint(30, 120)
        event_count = {"normal": rng.randint(0, 2), "interrupted": rng.randint(2, 5), "review_required": rng.randint(5, 9)}[behaviour]
        events = [
            {"event_type": rng.choice(["session_interaction", "brief_interruption", "reconnect"]),
             "timestamp": (started_at + timedelta(minutes=rng.randint(1, duration_minutes))).isoformat()}
            for _ in range(event_count)
        ]
        records.append({
            "candidate_reference": f"synthetic-candidate-{index + 1:04d}",
            "candidate_name": faker.name(),
            "session_reference": f"synthetic-session-{index + 1:04d}",
            "exam_identifier": f"EXAM-{rng.randint(1000, 9999)}",
            "status": "submitted",
            "started_at": started_at.isoformat(),
            "ended_at": (started_at + timedelta(minutes=duration_minutes)).isoformat(),
            "behaviour_pattern": behaviour,
            "events": events,
        })
    return records


def save_records(records, output_path=DEFAULT_OUTPUT):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic exam session logs.")
    parser.add_argument("--count", type=int, default=20, help="Number of session records to create.")
    parser.add_argument("--seed", type=int, help="Optional seed for repeatable output.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON output file path.")
    args = parser.parse_args()
    records = generate_session_records(args.count, args.seed)
    output = save_records(records, args.output)
    print(f"Generated {len(records)} synthetic session records at {output}")


if __name__ == "__main__":
    main()
