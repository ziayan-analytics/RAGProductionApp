# RAG Production App

A RAG-based AI knowledge agent for enterprise knowledge search. The demo connects Disc Medicine-style article data in MySQL, embeds it with OpenAI, stores vectors in Qdrant, and answers questions through a Streamlit UI.

## Stack

- Streamlit UI
- FastAPI backend
- Inngest workflows
- MySQL warehouse source
- Qdrant vector database
- OpenAI embeddings and answer generation

## Local Setup

```bash
cd "RAGProductionApp"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Start services:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
inngest-cli dev -u http://127.0.0.1:8000/api/inngest --no-discovery
streamlit run streamlit_app.py --server.port 8502
```

Open:

```text
http://localhost:8502
```

## Seed Demo Articles

```bash
mysql -e "CREATE DATABASE IF NOT EXISTS ragproductionapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql ragproductionapp < seed_disc_medicine_articles.sql
```

## Deployment Notes

Use managed services for production:

- MySQL: AWS RDS, Google Cloud SQL, PlanetScale, or company warehouse
- Qdrant: Qdrant Cloud
- Workflows: Inngest Cloud
- Secrets: provider environment variables, never committed to Git

`render.yaml` is included as a starting point for Render deployment.
