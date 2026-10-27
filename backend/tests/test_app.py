import pytest
from fastapi.testclient import TestClient

from app import main
from app.chunking import chunk_pages


def make_pdf(pages: list[str]) -> bytes:
    """Build a minimal valid PDF with one line of text per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content_ref = len(objs)
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ref} 0 R >>"
        )
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class FakeStore:
    def __init__(self, settings):
        self.docs: dict[str, dict] = {}

    def ensure_index(self):
        pass

    def delete_source(self, source):
        self.docs = {k: d for k, d in self.docs.items() if d["source"] != source}

    def upload(self, docs):
        self.docs.update({d["id"]: d for d in docs})

    def hybrid_search(self, query, vector, k):
        return list(self.docs.values())[:k]


class FakeLLM:
    def __init__(self, settings):
        self.last_sources = None

    def embed(self, texts):
        return [[0.0] * 3 for _ in texts]

    def answer(self, question, sources):
        self.last_sources = sources
        return "The sky is blue [1]."


@pytest.fixture
def client(monkeypatch):
    for k, v in {
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
        "AZURE_OPENAI_API_KEY": "x",
        "AZURE_SEARCH_ENDPOINT": "https://example.search.windows.net",
        "AZURE_SEARCH_API_KEY": "x",
    }.items():
        monkeypatch.setenv(k, v)
    main.get_settings.cache_clear()
    monkeypatch.setattr(main, "SearchStore", FakeStore)
    monkeypatch.setattr(main, "LLM", FakeLLM)
    with TestClient(main.app) as c:
        yield c


def test_chunk_pages_keeps_page_numbers_and_overlap():
    words = " ".join(f"w{i}" for i in range(400))
    chunks = chunk_pages(["", words, "short"], size=300, overlap=50)
    assert {c.page for c in chunks} == {2, 3}
    assert chunks[-1].text == "short"
    assert all(len(c.text) <= 300 for c in chunks)
    # consecutive chunks on the same page overlap
    assert chunks[0].text[-20:] in chunks[1].text
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_upload_then_ask(client):
    pdf = make_pdf(["The sky is blue.", "Grass is green."])
    r = client.post("/upload", files={"file": ("notes.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json() == {"filename": "notes.pdf", "pages": 2, "chunks": 2}

    # re-uploading replaces rather than duplicates
    client.post("/upload", files={"file": ("notes.pdf", pdf, "application/pdf")})
    assert len(main.app.state.store.docs) == 2

    r = client.post("/ask", json={"question": "What colour is the sky?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "The sky is blue [1]."
    assert body["sources"][0] == {"id": 1, "source": "notes.pdf", "page": 1, "snippet": "The sky is blue."}


def test_upload_rejects_non_pdf(client):
    r = client.post("/upload", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_ask_with_empty_index(client):
    r = client.post("/ask", json={"question": "anything?"})
    assert r.json() == {"answer": "No documents have been uploaded yet.", "sources": []}
