from fastapi import FastAPI, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import chromadb
import ollama
import pypdf
import json
import io
import requests
from docx import Document
from bs4 import BeautifulSoup
from ddgs import DDGS

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve frontend ────────────────────────────────────────────
FRONTEND_DIR  = os.path.join(os.path.dirname(__file__), "..", "frontend")
FRONTEND_FILE = os.path.join(FRONTEND_DIR, "index.html")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE)
    return {"message": "VaultMind API running. Frontend not found at ../frontend/index.html"}

@app.get("/manifest.json", include_in_schema=False)
async def serve_manifest():
    manifest = os.path.join(FRONTEND_DIR, "manifest.json")
    if os.path.exists(manifest):
        return FileResponse(manifest, media_type="application/manifest+json")
    return {}

# ── ChromaDB ──────────────────────────────────────────────────
chroma = chromadb.PersistentClient(path="./chroma_db")

EMBED_MODEL    = "nomic-embed-text"
DEFAULT_MODEL  = "mistral"

AVAILABLE_MODELS = [
    {"id": "mistral",       "label": "Mistral 7B"},
    {"id": "llama3.2",      "label": "Llama 3.2"},
    {"id": "phi3",          "label": "Phi-3 Mini"},
    {"id": "gemma2",        "label": "Gemma 2"},
    {"id": "qwen2.5",       "label": "Qwen 2.5"},
    {"id": "deepseek-r1",   "label": "DeepSeek R1"},
]

# ── Workspace helpers ─────────────────────────────────────────

def collection_name(workspace: str) -> str:
    """Map a workspace display name to a ChromaDB collection name."""
    if not workspace or workspace.strip().lower() in ("default", ""):
        return "vaultmind_docs"   # backward-compatible with Phase 1 data
    safe = workspace.strip().lower().replace(" ", "_").replace("-", "_")
    return f"vaultmind_{safe}"


def get_collection(workspace: str = "Default"):
    """Return (or create) the ChromaDB collection for a workspace."""
    return chroma.get_or_create_collection(collection_name(workspace))


def workspace_from_collection(col_name: str) -> str:
    """Convert a ChromaDB collection name back to a workspace display name."""
    if col_name == "vaultmind_docs":
        return "Default"
    if col_name.startswith("vaultmind_"):
        return col_name[len("vaultmind_"):].replace("_", " ").title()
    return col_name


# ── Workspaces API ────────────────────────────────────────────

@app.get("/workspaces")
async def list_workspaces():
    """Return all workspace names."""
    try:
        cols = chroma.list_collections()
        names = [
            workspace_from_collection(c.name)
            for c in cols
            if c.name == "vaultmind_docs" or c.name.startswith("vaultmind_")
        ]
    except Exception:
        names = []
    if not names:
        names = ["Default"]
    # Always put Default first
    if "Default" in names:
        names = ["Default"] + [n for n in names if n != "Default"]
    return {"workspaces": names}


class WorkspaceCreate(BaseModel):
    name: str

@app.post("/workspaces")
async def create_workspace(data: WorkspaceCreate):
    """Create a new workspace."""
    name = data.name.strip()
    if not name:
        return {"error": "Workspace name cannot be empty"}
    get_collection(name)   # creates collection if it doesn't exist
    return {"message": f"Workspace '{name}' created", "name": name}


# ── Models API ────────────────────────────────────────────────

@app.get("/models")
async def list_models():
    """Return available models and which ones are already pulled locally."""
    try:
        pulled_raw   = ollama.list()
        pulled_names = [m.model for m in pulled_raw.models]
    except Exception:
        pulled_names = []
    models = []
    for m in AVAILABLE_MODELS:
        is_available = any(m["id"] in p for p in pulled_names)
        models.append({**m, "available": is_available})
    return {"models": models, "default": DEFAULT_MODEL}


# ── Text helpers ──────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 150) -> list[str]:
    """Split text into overlapping chunks for precise retrieval."""
    words  = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - 20):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def extract_text_from_file(contents: bytes, filename: str) -> str:
    """Extract plain text from any supported file type."""
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = pypdf.PdfReader(io.BytesIO(contents))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        doc = Document(io.BytesIO(contents))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif name.endswith((".txt", ".md")):
        return contents.decode("utf-8", errors="ignore")
    elif name.endswith(".csv"):
        return contents.decode("utf-8", errors="ignore")
    return ""


def embed_and_store(chunks: list[str], source: str, col):
    """Embed chunks and upsert into a ChromaDB collection."""
    for i, chunk in enumerate(chunks):
        embedding = ollama.embeddings(model=EMBED_MODEL, prompt=chunk)["embedding"]
        col.upsert(
            ids=[f"{source}_{i}"],
            embeddings=[embedding],
            documents=[chunk],
            metadatas=[{"source": source, "chunk": i}]
        )
        if i % 10 == 0:
            print(f"  ✓ {i}/{len(chunks)}")


# ── Upload ────────────────────────────────────────────────────

@app.post("/upload")
async def upload_document(
    file:      UploadFile = File(...),
    workspace: str        = Form(default="Default")
):
    """Ingest a file into the specified workspace."""
    contents = await file.read()
    text     = extract_text_from_file(contents, file.filename)
    if not text.strip():
        return {"error": f"Could not extract text from '{file.filename}'. Supported: PDF, DOCX, TXT, MD, CSV"}
    chunks = chunk_text(text)
    print(f"\n📄 [{workspace}] Indexing '{file.filename}' — {len(chunks)} chunks")
    col = get_collection(workspace)
    embed_and_store(chunks, file.filename, col)
    print(f"✅ Done: '{file.filename}'")
    return {"message": f"Indexed {file.filename}", "chunks": len(chunks)}


# ── URL ingest ────────────────────────────────────────────────

class UrlIngest(BaseModel):
    url:       str
    workspace: str = "Default"

@app.post("/ingest-url")
async def ingest_url(data: UrlIngest):
    """Scrape a URL and index its content into the specified workspace."""
    BLOCKED_DOMAINS = ["indeed.com", "linkedin.com", "ziprecruiter.com", "glassdoor.com"]
    if any(d in data.url for d in BLOCKED_DOMAINS):
        return {
            "error": (
                "This site blocks scrapers. Try these instead:\n"
                "• Company career pages directly (e.g. greenhouse.io, lever.co, workday.com)\n"
                "• Google: https://www.google.com/search?q=data+engineer+jobs+irvine+ca\n"
                "• Builtin: https://builtin.com/jobs/data-engineer\n"
                "• Wellfound (AngelList): https://wellfound.com/jobs"
            )
        }
    try:
        r = requests.get(
            data.url, timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        if r.status_code == 403:
            return {"error": "This site blocks scrapers (403 Forbidden). Try the company's direct careers page instead."}
        if r.status_code == 429:
            return {"error": "Rate limited (429). Wait a minute and try again, or use a different URL."}
        r.raise_for_status()
    except requests.exceptions.Timeout:
        return {"error": "Request timed out. The site may be slow or blocking requests."}
    except Exception as e:
        return {"error": f"Could not fetch URL: {str(e)}"}

    soup  = BeautifulSoup(r.content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else data.url
    text  = soup.get_text(separator="\n", strip=True)
    if not text.strip():
        return {"error": "No readable content found at that URL."}

    source = f"🌐 {title[:80]}"
    chunks = chunk_text(text)
    print(f"\n🌐 [{data.workspace}] Indexing '{title}' — {len(chunks)} chunks")
    col = get_collection(data.workspace)
    embed_and_store(chunks, source, col)
    print(f"✅ Done: '{title}'")
    return {"message": f"Indexed {title}", "chunks": len(chunks), "source": source}


# ── Files list / delete ───────────────────────────────────────

@app.get("/files")
async def list_files(workspace: str = Query(default="Default")):
    """List all indexed sources in the specified workspace."""
    col     = get_collection(workspace)
    results = col.get(include=["metadatas"])
    files   = {}
    for meta in results["metadatas"]:
        src = meta["source"]
        files[src] = files.get(src, 0) + 1
    return {"files": [{"name": k, "chunks": v} for k, v in files.items()]}


@app.delete("/files/{filename}")
async def delete_file(filename: str, workspace: str = Query(default="Default")):
    """Remove a source from the specified workspace."""
    col     = get_collection(workspace)
    results = col.get(where={"source": filename}, include=["metadatas"])
    ids     = results["ids"]
    if not ids:
        return {"error": "File not found"}
    col.delete(ids=ids)
    print(f"🗑️  [{workspace}] Deleted '{filename}' ({len(ids)} chunks)")
    return {"message": f"Deleted {filename}", "chunks_removed": len(ids)}


# ── Chat ──────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    message:   str
    history:   list[dict] = []
    workspace: str = "Default"
    model:     str = "mistral"


@app.post("/chat")
async def chat(msg: ChatMessage):
    col                = get_collection(msg.workspace)
    chat_model         = msg.model or DEFAULT_MODEL
    question_embedding = ollama.embeddings(model=EMBED_MODEL, prompt=msg.message)["embedding"]
    results            = col.query(query_embeddings=[question_embedding], n_results=6)

    if not results["documents"][0]:
        def no_docs():
            yield f"data: {json.dumps({'token': 'No documents indexed yet in this workspace. Upload a file or paste a URL to get started.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
        return StreamingResponse(no_docs(), media_type="text/event-stream")

    context = "\n\n---\n\n".join(results["documents"][0])
    sources  = list(set(m["source"] for m in results["metadatas"][0]))

    messages = [
        {
            "role": "system",
            "content": (
                "You are a personal AI assistant. You have access ONLY to documents the user has explicitly indexed.\n\n"
                "STRICT RULES — follow these without exception:\n"
                "1. NEVER invent, fabricate, or guess information. No fake names, emails, phone numbers, job listings, companies, or URLs.\n"
                "2. ONLY use information that is literally present in the documents below.\n"
                "3. If the user asks for real-world data (live job listings, real candidate profiles, company contacts) that is NOT in the documents, respond with exactly this format:\n"
                "   'I don't have that data indexed. To get real results, paste the relevant URLs into VaultMind (e.g. a LinkedIn search page, a job board, a company careers page) and I can answer from that real data.'\n"
                "4. Never present strategies or instructions as if they are actual results. If you can only suggest a strategy, say clearly: 'I can suggest a strategy, but I don't have real data for this. Here is what to do to get it:'\n"
                "5. Be concise and direct. Do not pad responses.\n"
                "6. Write in plain prose only. NO markdown formatting — no bold (**text**), no headers (##), no bullet points, no dashes as list items. Just clean sentences and paragraphs.\n\n"
                f"INDEXED DOCUMENTS:\n{context}"
            )
        }
    ]
    for h in msg.history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": msg.message})

    def generate():
        stream = ollama.chat(model=chat_model, messages=messages, stream=True, options={"temperature": 0})
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ── Status / Health ───────────────────────────────────────────

@app.get("/status")
async def status(workspace: str = Query(default="Default")):
    """Return chunk count for the given workspace."""
    try:
        col   = get_collection(workspace)
        count = col.count()
    except Exception:
        count = 0
    return {"chunks_indexed": count, "status": "running", "workspace": workspace}


@app.get("/health")
async def health():
    try:
        models_raw  = ollama.list()
        model_names = [m.model for m in models_raw.models]
        has_embed   = any("nomic-embed-text" in m for m in model_names)
        has_llm     = any(
            any(x in m for x in ["mistral", "llama3", "phi3", "gemma", "qwen", "deepseek"])
            for m in model_names
        )
        return {"ollama": True, "embed_model": has_embed, "chat_model": has_llm, "ready": has_embed and has_llm}
    except Exception:
        return {"ollama": False, "embed_model": False, "chat_model": False, "ready": False}


# ─────────────────────────────────────────────────────────────
#  QUERY — non-streaming endpoint for programmatic use
# ─────────────────────────────────────────────────────────────

class QueryMessage(BaseModel):
    message:   str
    mode:      str = "vault"
    workspace: str = "Default"
    model:     str = "mistral"

@app.post("/query")
async def query(msg: QueryMessage):
    """Synchronous JSON endpoint for OpenClaw, scripts, and integrations."""
    try:
        col        = get_collection(msg.workspace)
        chat_model = msg.model or DEFAULT_MODEL
        q_emb      = ollama.embeddings(model=EMBED_MODEL, prompt=msg.message)["embedding"]

        vault_context = ""
        vault_sources = []
        RELEVANCE_THRESHOLD = 0.75
        v = col.query(query_embeddings=[q_emb], n_results=4, include=["documents", "metadatas", "distances"])
        if v["documents"][0]:
            relevant_docs = []
            relevant_meta = []
            for doc, meta, dist in zip(v["documents"][0], v["metadatas"][0], v["distances"][0]):
                if dist < RELEVANCE_THRESHOLD:
                    relevant_docs.append(doc)
                    relevant_meta.append(meta)
            if relevant_docs:
                vault_context = "\n\n".join(relevant_docs)
                vault_sources = list(set(m["source"] for m in relevant_meta))

        web_context = ""
        web_sources = []
        if msg.mode == "agent":
            hits = web_search(msg.message, max_results=4)
            for r in hits[:3]:
                text = smart_scrape(r.get("href", ""), max_chars=1500)
                if text:
                    web_context += f"\n\nSource: {r.get('title','')}\nURL: {r.get('href','')}\n{text}"
                    web_sources.append(r.get("title", r.get("href", "")))

        sections = []
        if vault_context:
            sections.append(f"FROM YOUR PRIVATE DOCUMENTS:\n{vault_context}")
        if web_context:
            sections.append(f"FROM THE WEB:\n{web_context}")
        if not sections:
            return {"answer": "I don't have any relevant information indexed for that question. Try adding documents or URLs in VaultMind first.", "sources": []}

        full_context = "\n\n---\n\n".join(sections)
        response = ollama.chat(
            model=chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a personal AI assistant. Answer the question using ONLY the sources below.\n"
                        "NEVER invent information. If the answer isn't in the sources, say so clearly.\n"
                        "Be concise and direct. Plain prose only — no markdown formatting.\n\n"
                        f"SOURCES:\n{full_context}"
                    )
                },
                {"role": "user", "content": msg.message}
            ],
            options={"temperature": 0}
        )
        answer = response["message"]["content"]
        return {"answer": answer, "sources": vault_sources + web_sources, "mode": msg.mode}

    except Exception as e:
        return {"error": str(e), "answer": "VaultMind encountered an error. Is Ollama running?"}


# ─────────────────────────────────────────────────────────────
#  AGENT LAYER — vault + live web search
# ─────────────────────────────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
}


def web_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"Search error: {e}")
        return []


def smart_scrape(url: str, max_chars: int = 2000) -> str:
    BLOCKED = ["linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com"]
    if any(d in url for d in BLOCKED):
        return ""
    try:
        r = requests.get(url, timeout=8, headers=BROWSER_HEADERS)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:max_chars]
    except Exception:
        return ""


@app.post("/agent")
async def agent(msg: ChatMessage):
    """Agent mode: vault search + live web search, streamed."""
    col        = get_collection(msg.workspace)
    chat_model = msg.model or DEFAULT_MODEL

    def generate():
        # ── Step 1: vault ──────────────────────────────────────
        vault_context = ""
        vault_sources = []
        RELEVANCE_THRESHOLD = 0.75
        try:
            q_emb = ollama.embeddings(model=EMBED_MODEL, prompt=msg.message)["embedding"]
            v     = col.query(query_embeddings=[q_emb], n_results=4, include=["documents", "metadatas", "distances"])
            if v["documents"][0]:
                rel_docs = []
                rel_meta = []
                for doc, meta, dist in zip(v["documents"][0], v["metadatas"][0], v["distances"][0]):
                    if dist < RELEVANCE_THRESHOLD:
                        rel_docs.append(doc)
                        rel_meta.append(meta)
                if rel_docs:
                    vault_context = "\n\n".join(rel_docs)
                    vault_sources = list(set(m["source"] for m in rel_meta))
        except Exception:
            pass

        # ── Step 2: web ────────────────────────────────────────
        yield f"data: {json.dumps({'status': '🔍 Searching the web...'})}\n\n"
        search_hits = web_search(msg.message, max_results=6)
        if not search_hits:
            yield f"data: {json.dumps({'status': '⚠️ No web results found, using vault only.'})}\n\n"

        web_context = ""
        web_sources = []
        scraped     = 0
        for hit in search_hits:
            if scraped >= 3:
                break
            url   = hit.get("href", "")
            title = hit.get("title", url)
            body  = hit.get("body", "")
            yield f"data: {json.dumps({'status': f'📄 Reading: {title[:50]}...'})}\n\n"
            page_text = smart_scrape(url) or body
            if page_text:
                web_context += f"\n\nSource: {title}\nURL: {url}\n{page_text}"
                web_sources.append(f"[{title}]({url})")
                scraped += 1

        yield f"data: {json.dumps({'status': '💬 Generating answer...'})}\n\n"

        # ── Step 3: build combined context ────────────────────
        sections = []
        if vault_context:
            sections.append(f"FROM YOUR PRIVATE DOCUMENTS:\n{vault_context}")
        if web_context:
            sections.append(f"FROM THE WEB (live results):\n{web_context}")

        if not sections:
            yield f"data: {json.dumps({'token': 'No relevant information found in your vault or on the web for this query.'})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
            return

        full_context = "\n\n" + "\n\n---\n\n".join(sections)
        all_sources  = vault_sources + web_sources

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a personal AI agent with access to both the user's private documents and live web search results.\n"
                    "Synthesize information from BOTH sources to give the most complete, accurate answer possible.\n"
                    "Clearly distinguish when information comes from private documents vs. the web.\n"
                    "NEVER invent or hallucinate information not present in the sources below.\n"
                    "Be direct and actionable.\n"
                    "Write in plain prose only. NO markdown formatting — no bold (**text**), no headers (##), no bullet points, no dashes as list items. Just clean sentences and paragraphs.\n\n"
                    f"SOURCES:\n{full_context}"
                )
            }
        ]
        for h in msg.history[-6:]:
            messages.append(h)
        messages.append({"role": "user", "content": msg.message})

        stream = ollama.chat(model=chat_model, messages=messages, stream=True, options={"temperature": 0})
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': all_sources})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
