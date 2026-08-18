# AnswerLens

AnswerLens is an AI brand-evidence and GEO-readiness auditing application. This repository currently contains only the development foundation; product features will be added in later tasks.

## Prerequisites

- Node.js 20.9 or newer
- Python 3.11 or newer

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:3000`.

## Backend

Create and activate a virtual environment, then run:

```bash
cd backend
python -m pip install -r requirements-dev.txt
uvicorn main:app --reload
```

The API is available at `http://localhost:8000`; its health check is `GET /health`.

Run backend tests with:

```bash
cd backend
python -m pytest
```

Copy `.env.example` to `.env` when future integrations require configuration. Do not commit `.env` files.
