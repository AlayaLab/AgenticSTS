import json, os, sys, datetime
from collections import defaultdict

LOG_DIR = "logs"
MIN_SIZE = 1024

logs_to_analyze = []
for fname in sorted(os.listdir(LOG_DIR)):
    if not fname.endswith('.jsonl') or not fname.startswith('run_'):
        continue
    fpath = os.path.join(LOG_DIR, fname)
    sz = os.path.getsize(fpath)
    if sz < MIN_SIZE:
        continue
    mtime = os.path.getmtime(fpath)
    dt = datetime.datetime.fromtimestamp(mtime)
    if dt.date() >= datetime.date(2026, 4, 20):
        logs_to_analyze.append((mtime, fname, fpath, sz))

logs_to_analyze.sort()

def read_log_lines(fpath, sz):
    lines = []
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        if sz > 5 * 1024 * 1024:
            for i, line in enumerate(f):
                if i >= 1000:
                    break
                lines.append(line)
            f.seek(0, 2)
            file_size = f.tell()
            seek_pos = max(0, file_size - 200*1024)
            f.seek(seek_pos)
            tail_content = f.read()
            tail_lines = tail_content.split('\n')[-500:]
            lines.extend(tail_lines)
        else:
            lines = f.readlines()
    return lines

results = []
for mtime, fname, fpath, sz in logs_to_analyze:
    lines = read_log_lines(fpath, sz)

    run_info = {
        'file': fname,
        'size_kb': sz // 1024,
        'outcome': None,
        'floor': 0,
        'character': None,
        'ascension': None,
        'model': None,
        'llm_calls': defaultdict(int),
        'llm_errors': 0,
        'stuck_count': 0,
        'errors': [],
        'error_msgs': defaultdict(int),
        'postrun_memory': False,
        'postrun_skill': False,
        'postrun_evolution': False,
        'death_enemy': None,
        'total_tokens': 0,
        'max_steps': 0,
    }

    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except:
            continue

        if not isinstance(entry, dict):
            continue

        event = entry.get('event', '')

        # Extract character from summary
        summary = entry.get('summary', '')
        if summary and run_info['character'] is None:
            parts = summary.split(' | ')
            if len(parts) >= 3:
                run_info['character'] = parts[2].strip()

        # Ascension
        asc = entry.get('ascension')
        if asc is not None and run_info['ascension'] is None:
            run_info['ascension'] = asc

        # Floor
        floor_val = entry.get('floor')
        if floor_val is not None:
            try:
                run_info['floor'] = max(run_info['floor'], int(floor_val))
            except:
                pass

        # Step
        step_val = entry.get('step')
        if step_val is not None:
            try:
                run_info['max_steps'] = max(run_info['max_steps'], int(step_val))
            except:
                pass

        # Model
        model = entry.get('model')
        if model and not run_info['model']:
            run_info['model'] = model

        # Outcome events
        if event in ('run_end', 'run_complete', 'run_result', 'run_summary'):
            outcome = entry.get('outcome')
            if outcome:
                run_info['outcome'] = outcome

        if event == 'defeat':
            run_info['outcome'] = 'defeat'
            run_info['death_enemy'] = entry.get('enemy') or entry.get('cause', 'unknown')

        if event in ('victory', 'run_victory'):
            run_info['outcome'] = 'victory'

        if event == 'max_steps_reached':
            run_info['outcome'] = 'max_steps'

        if event == 'agent_abort':
            run_info['outcome'] = 'agent_abort'

        # LLM calls
        if event == 'llm_call':
            state_type = entry.get('state_type', 'unknown')
            run_info['llm_calls'][state_type] += 1

        # LLM errors
        if event in ('llm_error', 'decision_error', 'api_error'):
            run_info['llm_errors'] += 1
            msg = entry.get('message', '') or entry.get('error', '')
            if msg:
                run_info['error_msgs'][str(msg)[:80]] += 1

        if event == 'llm_request_end':
            status = entry.get('status', '')
            if status != 'ok':
                run_info['llm_errors'] += 1
            tokens = entry.get('tokens', 0) or 0
            run_info['total_tokens'] += tokens
            model = entry.get('model')
            if model and not run_info['model']:
                run_info['model'] = model

        # Stuck
        if 'unstick' in event.lower() or event == 'force_unstick':
            run_info['stuck_count'] += 1

        # General errors
        if event in ('error', 'exception') or event.endswith('_error'):
            msg_text = entry.get('message', '') or str(entry.get('error', ''))
            if msg_text and len(msg_text) > 5:
                key = str(msg_text)[:80]
                run_info['error_msgs'][key] += 1
                if key not in run_info['errors']:
                    run_info['errors'].append(key)

        # Post-run pipeline
        evt_lower = event.lower()
        if any(x in evt_lower for x in ['memory_extract', 'postrun_memory', 'route_extract', 'card_build_extract']):
            run_info['postrun_memory'] = True
        if any(x in evt_lower for x in ['skill_discover', 'postrun_skill', 'write_skill', 'skill_write']):
            run_info['postrun_skill'] = True
        if any(x in evt_lower for x in ['evolution_start', 'evolution_end', 'evolution_result', 'evolv']):
            run_info['postrun_evolution'] = True
        stage = entry.get('stage', '')
        if 'memory_extract' in stage or 'route_extract' in stage:
            run_info['postrun_memory'] = True
        if 'skill_discover' in stage or 'skill_write' in stage:
            run_info['postrun_skill'] = True
        if 'evolution' in stage:
            run_info['postrun_evolution'] = True

    results.append(run_info)

print("=== TODAY'S RUN ANALYSIS (2026-04-20) ===")
print(f"Total logs: {len(results)}")
print()
for i, r in enumerate(results):
    llm_total = sum(r['llm_calls'].values())
    print(f"[{i+1}] {r['file']}")
    print(f"    Char={r['character']} | Asc={r['ascension']} | Model={r['model']}")
    print(f"    Outcome={r['outcome']} | Floor={r['floor']} | Steps={r['max_steps']}")
    print(f"    LLM_calls={llm_total} | LLM_errors={r['llm_errors']} | Stuck={r['stuck_count']} | Tokens={r['total_tokens']}")
    print(f"    PostRun: mem={r['postrun_memory']} skill={r['postrun_skill']} evo={r['postrun_evolution']}")
    if r['errors']:
        print(f"    Errors: {r['errors'][:3]}")
    print()
