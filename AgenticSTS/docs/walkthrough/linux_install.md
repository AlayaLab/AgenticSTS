# Linux install supplement

Supplements the [main README's Linux section](../../README.md#linux-wsl2--ubuntu--for-re-analysis-only) with troubleshooting tips and platform-specific quirks discovered while preparing the release.

> **Reminder**: Slay the Spire 2 has no native Linux build. On Linux you can
> recompute the paper's tables and figures from the released archive
> (`scripts/reproduce/*.py`), but you cannot collect new game trajectories
> without a Windows host running the mod. Cross-host setups are common —
> the game on Windows, analysis on a Linux workstation, with both pointing
> at the same `STS2_DATA_REPO`.

---

## Tested platforms

| Platform | Tested | Notes |
|---|---|---|
| Ubuntu 24.04 LTS (native) | yes (target) | Canonical Linux platform |
| WSL2 Ubuntu 24.04 on Windows 11 | yes | Recompute scripts work; cross-references between WSL `/mnt/d/...` and Windows `D:\...` paths need attention |
| Debian 12 | not tested | Should work with same apt packages |
| Fedora 40 | not tested | Substitute `dnf` for `apt`; package names may differ |
| macOS | not supported | Game unavailable on macOS; setup is best-effort if you only need recompute scripts |

---

## Python version pinning

`pyproject.toml` declares `requires-python = ">=3.12"`. The paper harness was
exercised on Python 3.14 (Windows). Recompute scripts run on 3.12+.

```bash
# Ubuntu 24.04 ships 3.12 by default; install 3.13 if you want to match the paper harness
sudo apt-get install -y python3.12 python3.12-venv

# Optional: install 3.13 from deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.13 python3.13-venv
```

If you see `ModuleNotFoundError: No module named 'X'`, double-check you
activated the right venv (`which python` should point inside `.venv/`).

---

## Optional dependency: matplotlib

`scripts/reproduce/reproduce_fig_3.py` and `reproduce_fig_4.py` use
matplotlib to render the figures. It's in the `eval` optional-dependency
group:

```bash
pip install -e ".[eval]"
# or, if you want all optional groups
pip install -e ".[dev,eval,monitor]"
```

Table-only scripts (`reproduce_table_2`, `reproduce_table_3`, `reproduce_app_2`)
have no matplotlib dependency.

---

## Setting `STS2_DATA_REPO` correctly

```bash
# Native Linux
export STS2_DATA_REPO="$(realpath ~/code/AgenticSTS-Data)"

# WSL2 — if the data repo is on Windows side, use the /mnt path
export STS2_DATA_REPO="/mnt/d/code/AgenticSTS-Data"

# Persist for future shells (Linux)
echo 'export STS2_DATA_REPO="$HOME/code/AgenticSTS-Data"' >> ~/.bashrc

# Persist (WSL2)
echo 'export STS2_DATA_REPO="/mnt/d/code/AgenticSTS-Data"' >> ~/.bashrc
```

Verify resolution:

```bash
python -c "import os; print('STS2_DATA_REPO =', os.environ.get('STS2_DATA_REPO'))"
ls "$STS2_DATA_REPO/runs/history.jsonl"
```

If `runs/history.jsonl` doesn't exist at the path you set, the recompute
scripts will fail with `FileNotFoundError`. Pull the data repo or fix the
path before running.

---

## WSL2 path quirks

When the data repo lives on the Windows side and you access it from WSL2:

| Issue | Symptom | Fix |
|---|---|---|
| Slow `history.jsonl` reads | `reproduce_table_2.py` takes 30+ s | Copy the JSONL into the WSL filesystem (`/home/...`) for I/O-heavy work — `/mnt/...` is on NTFS via the 9P bridge |
| Lockfile contention | `.postrun.lock` errors | Don't run agent and analysis simultaneously across the WSL/Windows boundary |
| Path comparisons | string mismatches in `experiment_tag` filters | Tags are pure ASCII; should not be affected |

The recompute scripts only **read** from `runs/history.jsonl`; they don't
write back. Cross-boundary reads are safe (just slow).

---

## Running individual recompute scripts

```bash
# Activate venv first
source .venv/bin/activate

# Table 2 — Fixed-A0 5-cell ablation
python -m scripts.reproduce.reproduce_table_2

# Table 3 — Cross-backbone probe
python -m scripts.reproduce.reproduce_table_3

# Figure 3 — bounded-memory token audit (requires matplotlib)
python -m scripts.reproduce.reproduce_fig_3

# Figure 4 — auto-mode ascension ladder (requires matplotlib)
python -m scripts.reproduce.reproduce_fig_4

# Appendix Table 2 — per-cell floor + boss-clear counts
python -m scripts.reproduce.reproduce_app_2

# All at once (returns non-zero if any cell diverges from snapshot)
bash scripts/reproduce/recompute_all.sh
```

If `recompute_all.sh` complains it's not executable:

```bash
chmod +x scripts/reproduce/recompute_all.sh
```

---

## Rebuilding the paper PDF (optional)

The paper bundle compiles under `pdflatex` + `bibtex`:

```bash
# TeX Live (large but complete)
sudo apt-get install -y texlive-base texlive-latex-extra texlive-bibtex-extra

cd paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents
pdflatex -interaction=nonstopmode main_v2.tex
bibtex main_v2
pdflatex -interaction=nonstopmode main_v2.tex
pdflatex -interaction=nonstopmode main_v2.tex
```

You need three `pdflatex` passes because float positions (Tables 2/3,
Figures 3/4) need to converge for the line-number package to align.

The compiled PDF should be byte-similar to the submitted version; minor
differences in package versions can shift line numbers within a baseline.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ImportError: cannot import name 'CELLS' from 'scripts.reproduce._lib'` | Older clone | `git pull origin main` |
| `FileNotFoundError: ... runs/history.jsonl` | `STS2_DATA_REPO` unset or wrong | See [Setting `STS2_DATA_REPO`](#setting-sts2_data_repo-correctly) |
| Recompute table values off by tiny amount | Different scipy version | Check `pip show scipy`; the paper used 1.14+ |
| Figure scripts skip with "matplotlib not found" | Optional dep missing | `pip install -e ".[eval]"` |
| Snapshot mismatch on a fresh clone | Possible bug | Open an issue with the diff between computed and snapshot values |
| Trajectory tags don't match `_lib.py` constants | Old data repo snapshot | Pull the sibling repo: `cd ../AgenticSTS-Data && git pull` |

---

## Cross-platform development workflow

A common setup for the EMNLP authors was:

```
Windows host  ─── STS2 + mod + agent ─── writes ───┐
                                                    ▼
                                             AgenticSTS-Data/
                                                    ▲
WSL2 (same host) ─── analysis scripts ─── reads ───┘
```

Both sides share `STS2_DATA_REPO`. The Windows side writes; the WSL side
reads. This kept the recompute pipeline fast (running in WSL is more
comfortable for pytest + jupyter), while gameplay stayed on Windows where
the game actually runs.

If you adopt a similar setup, keep these in mind:

1. `runs/history.jsonl` is append-only; the WSL side never writes back.
2. The `evolution/` subdirectory has per-run audit logs that the writer
   side may regenerate; the reader side shouldn't depend on them being
   stable.
3. The frozen $L_4{+}L_5$ snapshot at SHA `1888a62` is what the headline
   cells use. If you check out a different SHA, the recompute scripts
   should still work — but they'll be measuring the new snapshot, not the
   paper's.
