# PM Roadmap Agent

An agentic AI system that turns raw product feedback into a living roadmap brief.

Point it at App Store reviews, a CSV export, or a JSON dump. It clusters feedback into themes, tracks which themes are spiking, scores each one RICE-style, and writes the weekly roadmap brief a PM would actually share — with a human-in-the-loop UI so the PM stays in charge of every judgment call.

## Why this exists

Every PM does some version of this loop: read feedback → find patterns → figure out what's urgent → prioritize → communicate. It works at 50 pieces of feedback and breaks at 5,000. This project automates the mechanical parts (ingestion, dedupe, clustering, counting, arithmetic) while keeping the judgment parts (triage, effort estimates, final calls) with the human. That division of labor is the whole design philosophy — you'll see it in every module.

## Quickstart

```bash
git clone https://github.com/bandalok/pm-roadmap-agent.git
cd pm-roadmap-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# One-command offline demo (no API key needed):
python -m pm_roadmap_agent --demo
```

The demo runs the entire pipeline on bundled synthetic feedback for a fictional music app: 92 reviews across 8 weeks, including a deliberate spike in battery complaints. You'll see the trend detector flag it, the RICE ranking, and a generated `roadmap-brief-*.md`.

### With a real LLM

```bash
cp .env.example .env   # then set ANTHROPIC_API_KEY or OPENAI_API_KEY
```

```python
from pm_roadmap_agent import Config, run_pipeline
from pm_roadmap_agent.ingestors import AppStoreIngestor, CSVIngestor

config = Config()  # reads env vars
summary = run_pipeline(
    config,
    ingestors=[
        AppStoreIngestor(app_id=123456789, country="us", max_pages=5),
        CSVIngestor("exports/intercom.csv", text_column="message",
                    rating_column="csat", created_at_column="created_at"),
    ],
)
print(summary["brief_path"])
```

### The human-in-the-loop UI

```bash
streamlit run pm_roadmap_agent/ui/app.py
```

Review clustered themes, approve / reject / merge them, watch trend charts, inspect RICE rationales, and read the latest brief. Triage decisions persist to SQLite and are respected downstream — rejected and merged themes are never scored.

### Weekly digest

```bash
# Print the digest (safe default; great for cron)
python -m pm_roadmap_agent.digest --refresh

# ...or email it (needs SMTP_* in .env)
python -m pm_roadmap_agent.digest --refresh --email
```

## Architecture

```
 ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐
 │ App Store   │   │ CSV export  │   │ JSON dump        │
 │ RSS feed    │   │ (any tool)  │   │ (any shape)      │
 └──────┬──────┘   └──────┬──────┘   └────────┬─────────┘
        └─────────┬───────┴──────────┬────────┘
                  ▼                  ▼
           ┌────────────────────────────────┐
           │  Ingest → normalize → dedupe   │  (content-hash dedupe:
           │  → SQLite (append-only)        │   re-runs are idempotent)
           └───────────────┬────────────────┘
                           ▼
           ┌────────────────────────────────┐
           │  CLUSTER AGENT (LLM)           │  batch affinity-mapping,
           │  batch → themes → merge pass   │  then a merge pass so
           └───────────────┬────────────────┘  themes stay stable
                           ▼
           ┌────────────────────────────────┐
           │  TREND TRACKER                 │  per-week volume snapshots
           │  snapshots + spike detection   │  persisted; flags rising
           └───────────────┬────────────────┘  themes by velocity
                           ▼
           ┌────────────────────────────────┐
           │  SCORING AGENT (LLM)           │  model judges R/I/C/E with
           │  RICE = (R·I·C)/E in code      │  rationales; code does math
           └───────────────┬────────────────┘
                           ▼
           ┌────────────────────────────────┐
           │  BRIEF AGENT (LLM)             │  Markdown brief: every
           │  → briefs/roadmap-brief-*.md   │  claim cites a count
           └────────────────────────────────┘

        ┌──────────────┐         ┌──────────────────┐
        │ Streamlit UI │◄────────┤ approve / reject │
        │ (human loop) │         │ / merge themes   │
        └──────────────┘         └──────────────────┘
```

Key modules:

| Path | Role |
|---|---|
| `pm_roadmap_agent/pipeline.py` | Orchestrates the six stages; single entry point for CLI, UI, digest, demo |
| `pm_roadmap_agent/store.py` | SQLite layer: append-only feedback, theme triage states, snapshots, scores, runs |
| `pm_roadmap_agent/llm/` | Provider abstraction (`LLMProvider`) + Anthropic / OpenAI backends |
| `pm_roadmap_agent/prompts.py` | **All** prompts in one reviewed, commented file |
| `pm_roadmap_agent/ingestors/` | CSV, JSON, App Store (public iTunes lookup + reviews RSS — no scraping) |
| `pm_roadmap_agent/agents/` | Clustering, trend tracking, RICE scoring, brief writing, offline heuristics |
| `pm_roadmap_agent/ui/app.py` | Streamlit console for triage, trends, opportunities, brief |
| `pm_roadmap_agent/digest.py` | Weekly digest: print (default) or email via SMTP |
| `pm_roadmap_agent/demo.py` | One-command offline demo on synthetic data |

## How the agents work (and the PM reasoning behind them)

**Ingestion is dumb on purpose.** Every ingestor yields the same flat dict. The pipeline never knows where feedback came from, which means adding Intercom, Discourse, or G2 later is one small class, not a refactor.

**Dedupe is a content hash.** Re-running ingestion never double-counts a review. Idempotent pipelines are trustworthy pipelines.

**Clustering is batched, then merged.** Context windows are finite, so feedback is affinity-mapped in batches — then a second pass reunifies "app crashes" from batch 1 with "stability issues" from batch 2. Trends and RICE scores are only meaningful on stable, long-lived themes: the unit a roadmap is actually built on. Items the model drops are swept into "Uncategorized" — a clustering pass must never silently lose evidence.

**Trends measure velocity, not volume.** Fifty mentions over a year is backlog; fifty in a week is a fire. The detector is deliberately transparent — latest week ≥ 2× the recent baseline, with a minimum count — because a PM should be able to read the rule, disagree with it, and tune it.

**The model judges; the code does math.** RICE scoring asks the model for reach/impact/confidence/effort *with one-line rationales each*, then computes `(R·I·C)/E` in code. A single opaque number hides the judgment calls, and judgment calls are what the PM owns. Doing the arithmetic in code keeps every ranking reproducible and auditable.

**The brief cites counts.** The brief-writing agent leads with what changed, ranks opportunities in RICE order (it cannot reorder them), and every sentiment claim carries its feedback count. A brief without counts is just opinion. Caveats are a required section — sample size, source bias, date range — because honest uncertainty beats false precision.

**All prompts live in `prompts.py`.** Prompts are product copy: they get reviewed, versioned, and tested like any user-facing surface. Each one documents *why* it asks for what it asks for.

**The human stays in the loop.** The Streamlit UI is not a dashboard — it's a triage console. Approve what's real, reject noise, merge duplicates. Those decisions persist and the pipeline respects them downstream.

**Demo mode is deterministic.** With no API key, the pipeline swaps LLM agents for seeded heuristics (keyword taxonomy, volume-derived RICE, template brief). It's not as good as the LLM path and doesn't pretend to be — it exists so anyone can run the whole system in one command.

## Configuration

Everything is an environment variable (see `.env.example`); every one has a working default.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `LLM_MODEL` | `claude-haiku-4-5` / `gpt-4o-mini` | Model override |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Only needed for LLM runs |
| `DB_PATH` | `pm_roadmap_agent.db` | SQLite file |
| `BRIEFS_DIR` | `briefs` | Where briefs are written |
| `CLUSTER_BATCH_SIZE` | `40` | Feedback items per clustering call |
| `TREND_MIN_COUNT` / `TREND_GROWTH_FACTOR` | `3` / `2.0` | Spike-detector tuning |
| `APPSTORE_COUNTRY` / `APPSTORE_MAX_PAGES` | `us` / `5` | Review ingestion scope |
| `SMTP_*`, `DIGEST_TO` | — | Optional digest email |

## Testing

```bash
pytest tests/ -q
```

42 tests with a mocked LLM (`FakeProvider` in `tests/conftest.py`) — no API key, no network. Covers dedupe, ingestion (including a fixture App Store RSS feed), defensive JSON parsing, clustering id-sanitization, trend spike detection, RICE math and clamping, the full pipeline, and the offline demo.

## Roadmap

Ideas I'd explore next — roughly in priority order:

- **More ingestors**: Intercom, Zendesk, Discourse, Google Play reviews, G2/Capterra.
- **Embedding-based clustering**: replace/augment keyword + LLM batching with embedding similarity for 10k+ item corpora.
- **Theme identity across runs**: stable theme ids week-over-week (embedding centroid matching) so trends survive re-clustering.
- **Effort from your tracker**: pull real estimates from Jira/Linear instead of model priors.
- **Experiment suggestions**: link each opportunity to a concrete A/B test or prototype plan.
- **Slack digest**: post the weekly brief to a channel, not just email.
- **Eval harness**: a small labeled set measuring clustering precision/recall as prompts evolve.

## Contributing

This is a personal open-source project and a portfolio piece — issues and PRs are welcome. Please keep the design philosophy: automate the mechanical, keep judgment with the human, and put every prompt in `prompts.py` with a comment explaining the reasoning.

## License

MIT — see [LICENSE](LICENSE).
