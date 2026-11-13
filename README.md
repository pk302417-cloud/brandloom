# BrandLoom: pre-publication brand governance

Content goes in **before** it is published (post, advertisement, email, document or image). BrandLoom checks it against an
organisation's approved guidelines, facts, terminology and palette. Every finding names the rule or fact it breaks, quotes
the approved source, explains why, and suggests a fix. A human makes the final approval.

Built for the CodeNova India 2026 / Inkloom AI brand-governance challenge (Round 2: The Build).
The demo uses a **fictional brand ("Lumora")**. No real confidential material is included.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000      # open http://localhost:8000
```
Or `docker build -t brandloom . && docker run -p 8000:8000 brandloom`. Deploy: connect the repo to Render (`render.yaml`).
Set `SEED_DEMO=0` to start without demo content. Tests: `pip install -r requirements-dev.txt && pytest && python eval/run_eval.py`.

## Try it in 2 minutes (no walkthrough needed)
1. Open **Check content**, click **Messy social post**, then **Check content**.
2. Click a highlighted phrase or a finding card. Read the *Why* and the quoted *Source*.
3. **Accept fix** on a few findings (each creates a new revision), **Dismiss with reason** on another.
4. Switch user (top right) to **Morgan** or **Riley** and open the item from **Queue** to approve, request changes or reject.
5. Open **Insights** for recurring mistakes and guidelines that may be unclear, and **Brand library** to edit the approved sources.

## What works now
- Brand library: 20 guideline rules, 7 approved facts (with owners, sources, expiry and "supports claim"), palette, allowed acronyms. Add / switch off rules, add facts, export JSON.
- Review of text, Markdown/HTML, `.txt`, `.docx`, `.pdf` and images.
- Checks: terminology, tone, unsupported claims, health claims, competitor mentions, required promo wording, fact conflicts (numbers), outdated/expired information, link text, image alt text, sentence length, WCAG text contrast, palette conformity, image colours and resolution.
- Explainable findings: rule id, quoted source, reason, confidence, severity, suggested fix as a diff.
- Human control: accept, accept with own wording, or dismiss with required reason. Nothing is applied automatically.
- Workflow: roles (creator, manager, compliance reviewer), submit, approve / request changes / reject, no self-approval, claim and fact overrides need a Compliance Reviewer, comments, revision history with word-level diffs, audit log.
- Insights: issues by category, recurring mistakes per person, dismissal rate per rule, "possibly unclear" guideline detection.

## Architecture
```
static/ (HTML + vanilla JS SPA)  →  FastAPI (app/main.py)  →  SQLite (app/db.py)
                                         │
                                         └─ app/engine.py   deterministic review engine (no network calls)
```
- `engine.py` runs pure functions over text and the library, so results are reproducible and unit-testable.
- Each finding stores a fingerprint. Dismissals carry over to later revisions of the same text.
- `main.py` enforces roles and workflow rules on the server (the UI only mirrors them).

## Main technical decisions
- **Deterministic first.** Terms, numbers, formats, contrast and required wording are checked with code, so they are reliable and explainable. Judgement-based checks (tone, meaning) are left for the optional AI layer in Round 3, which must cite approved sources.
- **Grounded findings.** A finding cannot exist without a rule or approved fact behind it.
- **SQLite + FastAPI + vanilla JS** for a zero-setup deploy that judges can open without sign-in or a build step.

## Tools, services and AI disclosure
- Libraries: FastAPI, Uvicorn, python-docx, pypdf, Pillow, pytest.
- **No AI model and no external API is called by the running product in this version.** Nothing leaves the server.
- Development used AI assistance: Google Gemini (research), ChatGPT and Claude (planning, drafting and code assistance). All code was reviewed and run by the team.
- Datasets: none. All brand data is invented demo data (`app/seed.py`).
- Templates/boilerplate: none.

## Changes from the Round 1 plan
| Plan | Built in Round 2 | Why |
|---|---|---|
| Next.js + FastAPI + Supabase (pgvector) | Vanilla JS SPA + FastAPI + SQLite | Faster, simpler deploy; no sign-in needed for judges |
| LLM-based tone / claim analysis with citation verifier | Deterministic engine first | Reliability first; LLM layer is a Round 3 improvement |
| Supabase Auth and row-level security | Role switcher with server-side role checks | Demo scope; real auth is future work |
| Embedding retrieval over guideline text | Structured rules and facts | Exact, explainable matching |

## Known limitations
- Role switcher is not real authentication. Do not put real confidential data in this demo.
- The engine matches exact terms, patterns and numbers; it does not understand meaning.
- Scanned PDFs (no text layer) are not supported. Image checks are limited to alt text, colours and size.
- SQLite on free hosting may reset on redeploy. Demo content is re-seeded on start.

## Round 3 plan (three improvements)
1. **LLM-assisted tone and claim review with citation verification.** Findings must quote an approved source; a verifier rejects anything unsupported. Optional, labelled, and off by default.
2. **Intent-preserving rewrites.** Extract the creator's intent, propose rewrites, check intent is unchanged, show as diffs.
3. **Guideline-health insights and document accessibility.** Suggest clearer wording for rules people often dismiss, plus heading-structure and PDF/DOCX accessibility checks.
Also: real authentication, confidentiality tiers and redaction.

## Team
Team Alpha: Gaurav Kumar (team lead), Shimpy Kumari.
