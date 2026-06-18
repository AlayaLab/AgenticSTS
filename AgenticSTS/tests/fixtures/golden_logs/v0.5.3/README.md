# Golden Logs: v0.5.3

Frozen JSONL logs from pre-update runs. Each `run_*.jsonl` has a sibling `run_*.fingerprint.json`.

To freeze a new golden log:

    python -m scripts.freeze_golden_log logs/run_<id>.jsonl

Selection criteria: pick runs spanning ascension 0/4 victories, act2-boss loss, event-heavy, shop/rest-heavy.
