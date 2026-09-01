from scripts.generate_synthetic_data import generate_session_records, save_records


def test_generator_is_seeded_and_writes_requested_count(tmp_path):
    first = generate_session_records(count=3, seed=18)
    assert first == generate_session_records(count=3, seed=18)
    assert len(first) == 3
    assert {"candidate_reference", "session_reference", "started_at", "events"}.issubset(first[0])
    output = save_records(first, tmp_path / "records.json")
    assert output.exists()
