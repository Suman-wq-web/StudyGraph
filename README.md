# StudyGraph

Personal learning knowledge graph — save articles, videos, URLs, and notes; later, extract
concepts and relationships into a knowledge graph, ask questions over your own material with
RAG + citations, and get recommendations for what to learn next.

This repository is in **Phase 5 (hybrid retrieval + RAG chat, backend)**: resource CRUD
(Phase 2), document processing/chunking with `tiktoken` (Phase 3), and Gemini embeddings +
MongoDB **Atlas Vector Search** (Phase 4) are fully implemented end-to-end. Chat queries now run
through hybrid retrieval (Atlas Vector Search fused with Atlas Search BM25 via reciprocal rank
fusion), get grounded citations back to source resources, and stream a **Gemini**
(`gemini-3.6-flash`) answer over Server-Sent Events (`POST /api/v1/chat`). The frontend chat UI
(Vercel AI SDK wiring) and knowledge graph logic are not implemented yet — see
[`docs/ROADMAP.md`](./docs/ROADMAP.md) for what's next.

## Layout

- `frontend/` — Next.js 14+ (TypeScript, Tailwind CSS) app, deploys to Vercel.
- `backend/` — FastAPI (Python) app: API, RAG pipeline, knowledge graph pipeline, MongoDB access.
- `docs/` — full architecture and process documentation (see below).

## Quick start

```bash
# Frontend
cd frontend
npm install
npm run dev

# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
uvicorn main:app --reload
```

Copy `frontend/.env.local.example` → `frontend/.env.local` and `backend/.env.example` →
`backend/.env` first. Full instructions: [`docs/SETUP.md`](./docs/SETUP.md).

## Documentation

| Doc | Covers |
|---|---|
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System overview, frontend/backend structure, API boundaries |
| [SETUP.md](./docs/SETUP.md) | First-time install and run instructions |
| [DEVELOPMENT.md](./docs/DEVELOPMENT.md) | Conventions, testing, adding endpoints/pages |
| [API.md](./docs/API.md) | Endpoint contract, router map, conventions |
| [DATABASE.md](./docs/DATABASE.md) | MongoDB collections, fields, indexes |
| [RAG.md](./docs/RAG.md) | Retrieval-augmented generation pipeline design |
| [KNOWLEDGE_GRAPH.md](./docs/KNOWLEDGE_GRAPH.md) | Concept/relationship graph pipeline design |
| [DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Where and how each app deploys |
| [ENVIRONMENT.md](./docs/ENVIRONMENT.md) | Every environment variable, what reads it, why |
| [ROADMAP.md](./docs/ROADMAP.md) | Phased plan from this scaffold to a working product |
