from openai import AzureOpenAI

from .config import Settings

SYSTEM_PROMPT = """You answer questions using only the numbered sources provided.

Rules:
- Cite every factual claim with the source number in square brackets, e.g. [1] or [2][3].
- Only cite sources that actually support the claim.
- If the sources do not contain the answer, say you couldn't find it in the uploaded documents. Do not guess.
- Be concise."""


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 64):
            resp = self.client.embeddings.create(
                model=self.settings.azure_openai_embedding_deployment,
                input=texts[i : i + 64],
            )
            vectors.extend(d.embedding for d in resp.data)
        return vectors

    def answer(self, question: str, sources: list[dict]) -> str:
        context = "\n\n".join(
            f"[{n}] ({s['source']}, page {s['page']})\n{s['content']}" for n, s in enumerate(sources, start=1)
        )
        resp = self.client.chat.completions.create(
            model=self.settings.azure_openai_chat_deployment,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}"},
            ],
        )
        return resp.choices[0].message.content or ""
