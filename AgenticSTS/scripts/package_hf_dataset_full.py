"""Package the FULL AgenticSTS trajectory release as a Hugging Face dataset.

Two subsets in one dataset repo:

1. ``trajectories/`` — our agent's per-decision session logs (one gzipped JSONL
   per completed run), the full-fidelity record behind the paper's released
   archive: every state, decision, LLM call (with token usage), action result,
   and postrun stage. Selected from ``runs/history.jsonl`` (sibling data repo)
   with the paper's completed-game rule: outcome in {victory, defeat, max_steps},
   smoke/test rows excluded. Runs executed on teammate machines have a history
   row but no local session log (``has_trajectory: false`` in the manifest).
2. ``competitors/`` — raw captures for the two open-source accumulating-context
   baselines (STS2MCP, CharTyr), N=5 each (full LLM request/response + game I/O),
   reusing the per-run tar.gz archives staged by
   ``scripts.competitor_runs.package_hf_dataset``.

Sanitization (applied line-by-line to BOTH our trajectories AND the competitor
capture archives, which are decompressed/scrubbed/re-packed — sources never modified):
- commercial relay hostnames -> ``proxy.example.com``
- machine ids -> ``machine-N`` (case-insensitive; same mapping as the public repo)
- personal home dirs (POSIX + Windows, incl. third-party competitor operator paths
  like ``/Users/<name>/...``) -> ``/Users/operator`` / generic placeholder
- emails -> ``<email>`` (generic ``noreply@`` / ``example.*`` kept)
- defense-in-depth scan: any line matching a hard-secret pattern aborts the build

Usage:
  python -m scripts.package_hf_dataset_full --out dist/hf_dataset
  hf upload ShandaAI/AgenticSTS-trajectories dist/hf_dataset --repo-type dataset
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_REPO = Path(os.environ.get("STS2_DATA_REPO", str(REPO.parent / "AgenticSTS-Data")))
LOGS = REPO / "logs"
COMPETITOR_STAGING_PREFIXES = ("competitor-sts2mcp-gemini-A0-a", "competitor-chartyr-gemini-A0-a")

COMPLETED = {"victory", "defeat", "max_steps"}
EXCLUDE_MACHINES = {"smoke-test", "overlay-smoke"}
RUN_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")

REPLACEMENTS = [
    ("app.ppapi.ai", "proxy.example.com"),
    ("ppapi.ai", "proxy.example.com"),
    ("4sapi.com", "proxy.example.com"),
]
# Machine-id -> machine-N map for sanitizing run hostnames. Kept OUT of public source
# (raw hostnames are themselves identifying). Supply your own at packaging time via the
# SANITIZE_HOST_MAP env var as JSON, e.g.
#   SANITIZE_HOST_MAP='{"my-laptop":"machine-1","ci-box":"machine-2"}'
# Default empty: hostnames are not rewritten (already-sanitized data is unaffected; the
# home-dir / email / credential scrubbers below still run).
HOST_MAP = {k.lower(): v for k, v in json.loads(os.environ.get("SANITIZE_HOST_MAP", "{}")).items()}
HOST_RE = re.compile("(?i)(" + "|".join(re.escape(k) for k in HOST_MAP) + ")") if HOST_MAP else None
# personal home dirs -> generic placeholder, POSIX + Windows; generic names left alone.
# Catches our own (C:\Users\<name>) AND third-party operator paths in competitor captures
# (e.g. a competitor operator's /Users/<name>/...).
HOME_POSIX_RE = re.compile(r"(/Users/|/home/)(?!operator\b|user\b|runner\b|ci\b|root\b)[A-Za-z0-9._-]+")
HOME_WIN_RE = re.compile(r"(?i)([A-Za-z]:[\\/]+Users[\\/]+)(?!operator\b|public\b|default\b)[A-Za-z0-9._-]+")
# corporate / personal emails -> placeholder (generic noreply / example.* kept).
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.(?:com|org|net|edu|io|ai|cn)\b", re.I)
# any of these surviving a sanitized line is a build-stopping bug (hard secrets only).
CREDENTIAL_RE = re.compile(
    r"sk-[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{30}"
    r"|Bearer\s+[A-Za-z0-9._-]{20,}|AKIA[0-9A-Z]{16}"
)


def _email_sub(m: "re.Match") -> str:
    e = m.group(0)
    low = e.lower()
    return e if low.startswith("noreply@") or "@example." in low else "<email>"

CARD = """---
license: other
license_name: mixed-cc-by-4.0-plus-third-party
language: [en]
pretty_name: AgenticSTS trajectories + competitor-baseline captures
tags: [llm-agents, game-playing, slay-the-spire-2, agent-trajectories, bounded-memory]
---

> **License (mixed — read before reuse).** Our trajectories (`trajectories/`,
> `runs_history.jsonl`) and analysis are **CC-BY-4.0**. The `competitors/*.tar.gz`
> embed each competitor's own strategy/prompt documents under their upstream licenses
> (CharTyr/STS2-Agent is **AGPL-3.0**; STS2MCP under its own repo license) and are
> included verbatim for faithful-replication audit only --- **not** relicensed under
> CC-BY-4.0. All records reference *Slay the Spire 2*; underlying game IP remains with
> the rights holders. See the per-subset note below.

# AgenticSTS full trajectory release

The complete run-level + decision-level data behind the AgenticSTS paper
(*AgenticSTS: A Bounded-Memory Testbed for Long-Horizon LLM Agents*), plus the
raw captures of the two open-source accumulating-context baselines.

## Layout

| Path | Contents |
|---|---|
| `runs_history.jsonl` | run-level archive: one record per run (outcome, floor, condition tag, model profile snapshot, token/call counts) |
| `trajectories/<run_id>.jsonl.gz` | our agent's per-decision session log for that run: every state, decision, LLM call (token usage, latency, cache stats), action result, combat summary, postrun stage |
| `competitors/<run_id>.tar.gz` | raw captures for the STS2MCP / CharTyr baseline runs: `llm_calls.jsonl` (full prompts/responses), `game_io.jsonl`, `run_summary.json` |
| `manifest.json` | per-run index for both subsets |

## Our trajectories

**Run counts (298 / 312 / 385 — the same explanation appears on the repo and dataset).**
The paper's primary outcome analysis uses **298** victory/defeat games. This Hugging Face
release is a **312-record analysis superset**: the 298 paper games plus **14** decision-capped
(`max_steps`) runs kept for audit (298 + 14 = 312). The GitHub code repo's `runs/history.jsonl`
additionally lists **385** run-level audit rows --- the 298 completed games plus non-completing
harness rows (aborts, interrupts, decision-caps). Filtering `runs_history.jsonl` to
`outcome in {victory, defeat}` reproduces the paper's 298; the per-condition `experiment_tag`
map used by Table 2 / Table 3 is in `scripts/reproduce/_lib.py` in the
[code repository](https://github.com/ShandaAI/AgenticSTS). A few runs executed on teammate
machines have a history record but no session log (`has_trajectory: false`).

Most runs were played on Slay the Spire 2 v0.103.1; runs on or after 2026-06-12 were
played on v0.103.3. The per-run `game_version` is recorded in the manifest where
available; a small number of decision-capped/auxiliary records have no recorded game version.

## Competitor captures

N=5 completed games each for STS2MCP and CharTyr (author-intended configuration,
Gemini 3.1 Pro, Ascension 0, The Silent, game build v0.103.3, executed 2026-06-08..10).
Analysis conventions and aggregate results: `docs/experiments/competitor_comparison/RESULTS.md`
in the code repository.

> **License note (per-subset).** The `trajectories/` and `runs_history.jsonl` data are
> CC-BY-4.0 (this card's license). The `competitors/*.tar.gz` archives embed each
> competitor's own system-prompt / strategy documents, which remain under their
> upstream licenses — **CharTyr/STS2-Agent is AGPL-3.0**
> (https://github.com/CharTyr/STS2-Agent) and STS2MCP is under its own repo license
> (https://github.com/Gennadiyev/STS2MCP). Those embedded third-party documents are
> **not** relicensed under CC-BY-4.0; they are included verbatim for faithful-replication
> audit only, with attribution to their authors.

## Sanitization

Both our trajectories and the competitor archives are scrubbed line-by-line at packaging
time (the competitor `.tar.gz` are decompressed, scrubbed, and re-packed — not copied
verbatim): machine hostnames -> `machine-N`, commercial relay hostnames ->
`proxy.example.com`, personal home directories (including third-party competitor operator
paths) -> generic placeholders, emails -> `<email>`. A hard-secret scan (API keys, bearer
tokens) aborts packaging on any hit; no auth headers or API keys are present (the capture
proxy logs request bodies, not headers).
"""


def sanitize_line(line: str) -> str:
    for old, new in REPLACEMENTS:
        if old in line:
            line = line.replace(old, new)
    if HOST_RE is not None:
        line = HOST_RE.sub(lambda m: HOST_MAP[m.group(1).lower()], line)
    line = HOME_POSIX_RE.sub(lambda m: m.group(1) + "operator", line)
    line = HOME_WIN_RE.sub(lambda m: m.group(1) + "operator", line)
    line = EMAIL_RE.sub(_email_sub, line)
    return line


def _sanitize_tar_gz(src: Path, dst: Path) -> None:
    """Re-pack a competitor capture archive, sanitizing every text member line-by-line.

    Decompress -> scrub each line (sanitize_line) -> abort on any hard-secret hit ->
    re-pack. Binary/undecodable members pass through unchanged. This is what makes the
    dataset card's "no personal paths" claim true for competitor captures too (their
    prompts embed the competitor operator's home path)."""
    dst.unlink(missing_ok=True)
    with tarfile.open(src, "r:gz") as tin, tarfile.open(dst, "w:gz", compresslevel=6) as tout:
        for member in tin.getmembers():
            if not member.isfile():
                tout.addfile(member)
                continue
            data = tin.extractfile(member).read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                ti = tarfile.TarInfo(member.name)
                ti.size, ti.mtime, ti.mode = len(data), member.mtime, member.mode
                tout.addfile(ti, io.BytesIO(data))
                continue
            out = []
            for line in text.splitlines(keepends=True):
                s = sanitize_line(line)
                hit = CREDENTIAL_RE.search(s)
                if hit:
                    dst.unlink(missing_ok=True)
                    raise SystemExit(f"ABORT: credential pattern {hit.group()[:12]}… in {src.name}:{member.name}")
                out.append(s)
            blob = "".join(out).encode("utf-8")
            ti = tarfile.TarInfo(member.name)
            ti.size, ti.mtime, ti.mode = len(blob), member.mtime, member.mode
            tout.addfile(ti, io.BytesIO(blob))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/hf_dataset")
    ap.add_argument("--competitor-staging", default="dist/hf_dataset_competitors",
                    help="dir holding competitor <run>.tar.gz (from package_hf_dataset)")
    args = ap.parse_args()
    out = Path(args.out)
    traj_dir = out / "trajectories"
    comp_dir = out / "competitors"
    traj_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)

    # ---- subset 1: our trajectories -------------------------------------
    manifest: dict[str, list] = {"trajectories": [], "competitors": []}
    hist_out = []
    n_logs = n_nolog = 0
    for raw in (DATA_REPO / "runs" / "history.jsonl").read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        sraw = sanitize_line(raw)
        hit = CREDENTIAL_RE.search(sraw)
        if hit:
            raise SystemExit(f"ABORT: credential pattern {hit.group()[:12]}… in history.jsonl")
        r = json.loads(sraw)
        rid = str(r.get("run_id", ""))
        if not RUN_ID_RE.match(rid):
            continue
        if r.get("outcome") not in COMPLETED:
            continue
        if r.get("machine_id") in EXCLUDE_MACHINES:
            continue
        hist_out.append(json.dumps(r, ensure_ascii=False))
        src = LOGS / f"run_{rid}.jsonl"
        has = src.exists()
        if has:
            dst = traj_dir / f"{rid}.jsonl.gz"
            if not dst.exists():  # resumable
                with open(src, encoding="utf-8", errors="replace") as fin, \
                        gzip.open(dst, "wt", encoding="utf-8", compresslevel=6) as fout:
                    for line in fin:
                        line = sanitize_line(line)
                        m = CREDENTIAL_RE.search(line)
                        if m:
                            dst.unlink(missing_ok=True)
                            raise SystemExit(f"ABORT: credential-like pattern {m.group()[:12]}… in {src}")
                        fout.write(line)
            n_logs += 1
        else:
            n_nolog += 1
        manifest["trajectories"].append({
            "run_id": rid,
            "outcome": r.get("outcome"),
            "final_floor": r.get("final_floor"),
            "ascension": r.get("target_ascension"),
            "character": r.get("character"),
            "experiment_tag": r.get("experiment_tag") or None,
            "machine": r.get("machine_id"),
            "game_version": r.get("game_version"),
            "has_trajectory": has,
            "file": f"trajectories/{rid}.jsonl.gz" if has else None,
        })
    (out / "runs_history.jsonl").write_text("\n".join(hist_out) + "\n", encoding="utf-8")
    print(f"trajectories: {n_logs} packed, {n_nolog} history-only (teammate machines)")

    # ---- subset 2: competitor captures ----------------------------------
    staging = Path(args.competitor_staging)
    comp_manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8")) \
        if (staging / "manifest.json").exists() else []
    for entry in comp_manifest:
        arc = staging / entry["archive"]
        if not arc.name.startswith(COMPETITOR_STAGING_PREFIXES):
            continue
        dst = comp_dir / arc.name
        _sanitize_tar_gz(arc, dst)
        entry["file"] = f"competitors/{arc.name}"
        entry["bytes"] = dst.stat().st_size
        manifest["competitors"].append(entry)
    print(f"competitors: {len(manifest['competitors'])} archives re-packed (sanitized)")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "README.md").write_text(CARD, encoding="utf-8")
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"\nstaged -> {out}  ({total/1e9:.2f} GB, "
          f"{len(manifest['trajectories'])} runs + {len(manifest['competitors'])} competitor archives)")
    print("upload:  hf upload ShandaAI/AgenticSTS-trajectories", out, "--repo-type dataset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
