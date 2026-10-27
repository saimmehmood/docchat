from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


@dataclass
class Chunk:
    text: str
    page: int  # 1-based page where the chunk starts
    index: int


def extract_pages(data: bytes) -> list[str]:
    reader = PdfReader(BytesIO(data))
    return [(page.extract_text() or "") for page in reader.pages]


def chunk_pages(pages: list[str], size: int = 1200, overlap: int = 200) -> list[Chunk]:
    """Split page text into overlapping character windows.

    Chunks never span pages, so every chunk maps to exactly one page number
    that can be cited back to the user.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    chunks: list[Chunk] = []
    step = size - overlap
    for page_no, raw in enumerate(pages, start=1):
        text = " ".join(raw.split())
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            # Prefer to break on whitespace so words aren't cut in half.
            if end < len(text):
                space = text.rfind(" ", start + step, end)
                if space != -1:
                    end = space
            chunks.append(Chunk(text=text[start:end].strip(), page=page_no, index=len(chunks)))
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks
