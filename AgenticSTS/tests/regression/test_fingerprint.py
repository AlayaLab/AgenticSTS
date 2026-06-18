from src.regression.log_replay import compute_fingerprint


def test_fingerprint_counts_decisions():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "v2_strategic", "state_type": "shop"},
    ]
    fp = compute_fingerprint(decisions)
    assert fp["num_decisions"] == 3
    assert fp["decision_types"]["combat"] == 2
    assert fp["decision_types"]["shop"] == 1
    assert fp["source_distribution"]["v2_fast"] == 2
    assert fp["source_distribution"]["v2_strategic"] == 1


def test_fingerprint_stable_across_identical_inputs():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
    ]
    assert compute_fingerprint(decisions) == compute_fingerprint(list(decisions))


def test_fingerprint_tracks_errors():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "error", "state_type": "combat", "error": "timeout"},
    ]
    fp = compute_fingerprint(decisions)
    assert fp["error_count"] == 1
