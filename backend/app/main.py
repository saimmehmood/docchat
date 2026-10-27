import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chunking import chunk_pages, extract_pages
from .config import get_settings
from .llm import LLM
from .search import SearchStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.store = SearchStore(settings)
    app.state.llm = LLM(settings)
    await run_in_threadpool(app.state.store.ensure_index)
    yield


app = FastAPI(title="DocChat", lifespan=lifespan)


class UploadResponse(BaseModel):
    filename: str
    pages: int
    chunks: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Source(BaseModel):
    id: int
    source: str
    page: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


def _doc_id(source: str, chunk: int) -> str:
    # Search keys allow only letters, digits, '_', '-', '='; urlsafe base64 fits.
    return base64.urlsafe_b64encode(f"{source}:{chunk}".encode()).decode()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "PDF is larger than 20 MB")

    settings = app.state.settings
    filename = Path(file.filename).name
    try:
        pages = await run_in_threadpool(extract_pages, data)
    except Exception:
        raise HTTPException(400, "Could not read PDF")

    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise HTTPException(422, "No extractable text found (scanned PDFs need OCR)")

    vectors = await run_in_threadpool(app.state.llm.embed, [c.text for c in chunks])
    docs = [
        {
            "id": _doc_id(filename, c.index),
            "content": c.text,
            "source": filename,
            "page": c.page,
            "chunk": c.index,
            "embedding": v,
        }
        for c, v in zip(chunks, vectors)
    ]
    await run_in_threadpool(app.state.store.delete_source, filename)
    await run_in_threadpool(app.state.store.upload, docs)
    return UploadResponse(filename=filename, pages=len(pages), chunks=len(chunks))


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    settings = app.state.settings
    [vector] = await run_in_threadpool(app.state.llm.embed, [req.question])
    hits = await run_in_threadpool(app.state.store.hybrid_search, req.question, vector, settings.top_k)
    if not hits:
        return AskResponse(answer="No documents have been uploaded yet.", sources=[])

    answer = await run_in_threadpool(app.state.llm.answer, req.question, hits)
    sources = [
        Source(id=n, source=h["source"], page=h["page"], snippet=h["content"][:300])
        for n, h in enumerate(hits, start=1)
    ]
    return AskResponse(answer=answer, sources=sources)


# Serve the built React app (copied in by the Dockerfile) at /.
static_dir = Path(os.getenv("STATIC_DIR", Path(__file__).parent.parent / "static"))
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
