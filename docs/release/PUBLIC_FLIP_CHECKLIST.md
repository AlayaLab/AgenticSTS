# Public-flip checklist

The GitHub repo (`ShandaAI/AgenticSTS`) and the HF dataset
(`ShandaAI/AgenticSTS-trajectories`) are **private** today. This is the procedure
to follow before making either public. It folds in the remaining blockers from the
2026-06-12 release risk audit (`release_risk_report` in the review package).

## 0. Gate: ARR anonymity (BLOCKER H2)

The paper is under anonymous EMNLP ARR review. The org name "ShandaAI" + the
"Shanda AI Research" copyright lines **are the affiliation** — making the repo
public during review deanonymizes the submission. **Do not flip either artifact
public until the ARR anonymity window has lifted** (camera-ready / withdrawal /
explicit permission). Everything below is the *mechanics*; this gate is the
*timing*.

## 1. Re-seed git history (BLOCKER B1) — requires force-push

`git log` currently exposes real author names + a corporate email
(`<author> <name@corp-domain>`) across the commit history, and earlier commits
still contain the now-removed proprietary game files (B2) and the `.postrun.lock`
(B3). A normal push does **not** fix this — the leak is in history. Re-seed to a
single clean commit from the current (already-remediated) tree:

```bash
cd /path/to/AgenticSTS            # the remediated clone
# sanity: working tree must be clean and contain NO proprietary files / locks
git status --porcelain            # expect empty
git ls-files | grep -E "localization/|afflictions.json|powers.json|\.postrun\.lock" # expect empty

git checkout --orphan release-clean
git add -A
git -c user.name="AgenticSTS" -c user.email="agenticsts@users.noreply.github.com" \
    commit -m "AgenticSTS: initial public release"
git branch -D main
git branch -m main
# REVIEW the single commit's author/committer and file list before pushing:
git log --format='%aN <%aE> | %cN <%cE>'        # expect ONE neutral identity
git ls-files | wc -l
git push --force origin main      # <-- destructive remote rewrite; do only when ready
```

After the force-push, verify on GitHub that `git log` shows one neutral commit and
that the deleted files do not appear in any historical blob (`git rev-list --all`).

## 2. arXiv version (L19–L21) — only at preprint-post time

The deanonymized arXiv source (`paper/.../main.tex`, not in this repo) carries the
real author block + `\github`/`\Code` URLs (already pointed at `ShandaAI/AgenticSTS`
+ the HF dataset). Switch any remaining anonymous-review wording
("anonymized archive/release") to "public/released", resolve the author-block TODOs,
and post only after the anonymity gate (§0).

## 3. Flip the artifacts public

```bash
# GitHub
gh repo edit ShandaAI/AgenticSTS --visibility public --accept-visibility-change-consequences
# Hugging Face (after re-confirming the card + a final sensitive scan)
hf repo update ShandaAI/AgenticSTS-trajectories --private false
```

## 4. Final pre-flip verification

```bash
# no secrets / hosts / personal paths / emails anywhere in the tree
grep -rIE "sk-[A-Za-z0-9]{20}|hf_[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{30}|Bearer\s+[A-Za-z0-9._-]{20}" . --exclude-dir=.git
# relay vendor + your team's machine ids + corporate email domain (fill in YOUR values):
grep -rIE "4sapi|ppapi|<your-machine-hostnames>|@<your-corp-domain>" . --exclude-dir=.git \
     --exclude=package_hf_dataset_full.py   # sanitizer legitimately maps these
grep -rIE "C:[\\/]+Users[\\/]+[a-z]+|/Users/[a-z]+|/home/[a-z]+" . --exclude-dir=.git   # personal home paths
# no proprietary game content tracked
git ls-files | grep -E "data/knowledge/localization/|afflictions.json|powers.json|_dll.json|upstream/"
# citation updated with arXiv id (after preprint posts)
grep -n "Under review" README.md
```

All greps should return empty (except the sanitizer's own map, and generic
home-path placeholders like `/Users/operator`). Substitute your real machine
hostnames / corporate email domain into the second grep before running. Then flip.

## Status (2026-06-12)

| Item | State |
|---|---|
| B2 proprietary game files | **fixed** — removed from tree + `.gitattributes`/`.gitignore` + regeneration documented |
| B3 `.postrun.lock` | **fixed** — untracked + ignored |
| H1/H3/H4 HF card (license, counts) | **fixed** — card updated, dataset re-uploaded |
| H5 arXiv URLs | **fixed** — point at ShandaAI |
| H6/M1/M2/M3/M4/M5/M6/M7/M9 docs+code | **fixed** in the remediation commit |
| **B1 git history** | **pending** — §1 re-seed (force-push, needs approval) |
| **H2 anonymity timing** | **pending** — §0 gate |
| arXiv author block | **pending** — §2, at preprint-post time |
