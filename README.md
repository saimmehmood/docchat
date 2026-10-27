# DocChat

Upload PDFs and ask questions about them. Answers cite the pages they came from.

- **Backend:** FastAPI. `POST /upload` extracts text from a PDF, splits it into overlapping chunks per page, embeds them with Azure AI Foundry and indexes them in Azure AI Search. `POST /ask` runs a hybrid (keyword + vector) search, sends the top chunks to the chat model as numbered sources, and returns the answer with `[n]` citations plus the source list.
- **Frontend:** a single React page (Vite) with an upload button and a chat box. In production FastAPI serves the built page at `/`.
- **Deploy:** one Docker image, pushed to Azure Container Registry and deployed to Azure App Service by GitHub Actions.

```
backend/app/        FastAPI app (main.py, chunking.py, search.py, llm.py, config.py)
backend/tests/      pytest tests (Azure is faked)
frontend/           React + Vite UI
infra/provision.sh  Azure CLI script that creates all resources
Dockerfile          multi-stage build: frontend → Python image
.github/workflows/  test + build + deploy
```

## 1. Provision Azure

Requires the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and, optionally, a logged-in `gh` CLI.

```bash
az login
./infra/provision.sh            # e.g. LOCATION=swedencentral ./infra/provision.sh
```

This creates, in resource group `rg-docchat`:

| Resource | SKU | Purpose |
|---|---|---|
| Azure AI Foundry (AI Services) | S0 | `gpt-4.1-mini` chat deployment, `text-embedding-3-small` embedding deployment |
| Azure AI Search | **Free** | vector + keyword index (created by the app on first start) |
| Container Registry | Basic | holds the Docker image |
| App Service plan + Web App | B1 Linux | runs the container |

It writes `backend/.env` for local development and stores the deployment secrets on the GitHub repo (`AZURE_WEBAPP_NAME`, `AZURE_WEBAPP_PUBLISH_PROFILE`, `ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD`).

Notes:
- Each subscription can have only one free Search service. If you already have one, set `SEARCH_NAME` to it and remove the create line.
- Model availability and quota differ by region. If a deployment fails, try another `LOCATION` or set `CHAT_MODEL`/`CHAT_MODEL_VERSION`.
- The free Search tier holds 50 MB, which is enough for a few thousand chunks.

## 2. Deploy

Push to `main`. The workflow runs the tests, builds the image, pushes it to ACR, and deploys it to App Service. If the Azure secrets aren't set yet, the deploy step is skipped with a warning.

## Run locally

```bash
# API (reads backend/.env)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload

# UI (proxies /upload and /ask to :8000)
cd frontend
npm install && npm run dev
```

Or run the full container: `docker build -t docchat . && docker run -p 8000:8000 --env-file backend/.env docchat`.

## Tests

```bash
cd backend && .venv/bin/pip install pytest httpx && .venv/bin/python -m pytest
```

## Limitations

- Only text-based PDFs work. Scanned PDFs need OCR, for example Azure Document Intelligence.
- Re-uploading a file with the same name replaces its chunks.
- There is no authentication, so anyone with the URL can upload documents and ask questions. Add App Service Authentication (Easy Auth) before you share it.
