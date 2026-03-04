# VaultMind Launch Content

Today is Wednesday March 4. Post HN between 8-10am EST for best traction.

---

## Hacker News — Show HN

**Title:**
```
Show HN: VaultMind – chat with your documents and the web using local LLMs, no cloud
```

**First comment (post immediately after the submission):**
```
Built this over a few days. The core idea: you have files you'd never
upload to ChatGPT — contracts, financial docs, personal notes, work SOPs.
But you still want to ask questions about them in plain English.

Stack: FastAPI + ChromaDB + Ollama (mistral + nomic-embed-text).
The entire UI is a single HTML file. Nothing touches a server.

What it does:
- Ingest PDFs, Word docs, TXT, Markdown, CSV files
- Ingest URLs (scrapes and indexes the content locally)
- Chat with your indexed docs — streamed answers, conversation memory
- Agent mode: searches your vault AND DuckDuckGo simultaneously,
  synthesizes both into one answer

The relevance filtering was the interesting part to get right. ChromaDB
returns distance scores — if nothing in the vault is close enough to the
query, we skip vault context entirely and go straight to web search.
Stops the model from hallucinating connections between unrelated docs.

Setup wizard handles Ollama install checks, model pulls, and backend
health before letting you in. One-command launcher: bash start.sh

It's early. The scraper gets blocked by LinkedIn, Indeed, Glassdoor
(expected). Works well with Greenhouse, Lever, Wellfound, and most
static content sites.

Part of the AIR Blackbox ecosystem (airblackbox.ai) — same local-first
philosophy as the EU AI Act compliance scanner.

Repo: https://github.com/airblackbox/VaultMind
```

---

## Twitter/X Thread

```
1/
Your documents have things you'd never paste into ChatGPT.

Contracts. SOPs. Medical records. Personal notes. Company data.

I built VaultMind — chat with your files and the live web using
local LLMs. Zero cloud. Runs on your Mac in 5 minutes.

Here's what I shipped:

2/
The stack is boring on purpose:
- FastAPI backend
- ChromaDB (vector store, persists on disk)
- nomic-embed-text for embeddings
- mistral for inference
- UI is a single HTML file

All running locally via Ollama. Nothing leaves your machine.

3/
Two modes:

Vault mode: answers come only from your indexed docs.
Ask "what are the payment terms in this contract?" and it
cites the actual source.

Agent mode: searches your vault + DuckDuckGo simultaneously.
Synthesizes both into one answer. Real-time status as it works.

4/
The part that took the most work: relevance filtering.

ChromaDB returns distance scores. If nothing in your vault
is close enough to the query, we skip the vault entirely.

"Recap the news today" goes straight to web search.
"What's our website CTR?" hits your indexed docs.

5/
Supports PDF, Word, TXT, Markdown, CSV, and URLs.
Paste a job board URL, a competitor's page, a news article —
it gets scraped, chunked, embedded, and indexed locally.

Setup wizard walks you through everything.
One command: bash start.sh

Apache 2.0. github.com/airblackbox/VaultMind
```

---

## LinkedIn

```
Shipped VaultMind this week — a private document AI that runs
entirely on your machine.

The pitch is simple: you have files you'd never upload to ChatGPT.
Contracts, financial statements, SOPs, medical records, client notes.
VaultMind lets you chat with those files in plain English — with zero
data leaving your computer.

Drop in a PDF, paste a URL, or drag in a CSV. It chunks and indexes
everything locally using ChromaDB and Ollama. Ask questions, get
streamed answers backed by your actual source documents.

Agent mode goes further — it searches your private vault and the live
web simultaneously, then synthesizes both into one answer. The
relevance filtering skips vault context automatically when your docs
aren't related to the query.

It's early. Works well for knowledge bases, recruiting research, SOPs,
and any situation where you want a private AI that knows your stuff.

Built as part of the AIR Blackbox ecosystem (airblackbox.ai).
Same local-first philosophy as the EU AI Act compliance scanner.

Open source, Apache 2.0. Repo in the comments.

#OpenSource #LocalAI #RAG #Privacy #Ollama
```

---

## Reddit

**r/LocalLLaMA title:**
```
Built a local RAG system that searches your docs + the web —
Ollama + ChromaDB + FastAPI, relevance filtering to avoid hallucination
```

**r/selfhosted title:**
```
VaultMind – chat with your local documents and live web using Ollama.
Single HTML UI, bash start.sh launcher, zero cloud.
```

**Body for both:**
```
Built this over a few days. Quick start:

git clone https://github.com/airblackbox/VaultMind
cd VaultMind
bash start.sh

That's it. The script handles Ollama, model pulls (nomic-embed-text +
mistral), Python deps, and opens the UI.

Supports: PDF, DOCX, TXT, MD, CSV, and URL scraping.

Two modes:
- Vault: answers from your indexed docs only
- Agent: vault + DuckDuckGo, relevance-filtered

Apache 2.0. Happy to answer questions about the RAG pipeline.
```
