# DoubleHelixGraphRAG

**Version 1.0.0**

---

**DoubleHelixGraphRAG** is an industrial-grade, lightweight, and hyper-adaptive Python library for building sophisticated Retrieval-Augmented Generation (RAG) systems. It is built from the ground up with a "no black boxes" philosophy, eschewing monolithic frameworks like LangChain or LlamaIndex in favor of a modular, transparent, and fully-controllable architecture.

This library is designed for production environments where security, scalability, observability, and total control over the data and retrieval process are paramount.

## Core Philosophy

- **Industrial-Grade**: Built with production-ready components like FastAPI, Celery, Redis, SQLAlchemy, and Neo4j.
- **Lightweight & Modular**: Each component (parsing, chunking, embedding, retrieval) is a distinct, swappable module.
- **Hyper-Adaptive**: LLM-agnostic, storage-agnostic, and highly configurable through environment variables.
- **No Black Boxes**: Every step of the pipeline is explicit and customizable. You have full control over prompts, data flow, and retrieval logic.
- **Evaluation-Driven**: Integrated, automated RAG evaluation with `ragas` is a first-class citizen, enabling continuous quality monitoring and preventing performance regressions.

## Features

- **Asynchronous Ingestion Pipeline**: Scalable document processing using Celery and Redis, with retries, backoff, and a dead-letter queue.
- **Real Knowledge Graph**: Automatically extracts entities and relationships from documents and resolves them to build a canonical graph in Neo4j, preventing data silos.
- **Hybrid Retrieval**: Combines semantic vector search with contextual graph traversal, using Reciprocal Rank Fusion (RRF) to intelligently merge results.
- **Full Document Lifecycle**: Create, update, and delete documents with automatic, clean garbage collection of orphaned nodes and relationships in the graph.
- **Streaming & Citations**: FastAPI endpoints provide a streaming response for real-time generation, with source citations included in the response headers.
- **Cost & Observability**: Built-in cost estimation with `tiktoken` and structured JSON logging for comprehensive monitoring.
- **Secure & Configurable**: All settings managed via `.env` files. API secured with Bearer token authentication.

---

## System Architecture

The system is composed of several key services, orchestrated by Docker Compose for local development:

1.  **FastAPI App (`api`)**: The main entrypoint, providing REST endpoints for all operations.
2.  **Celery Worker (`worker`)**: Handles the heavy lifting of document ingestion asynchronously.
3.  **Neo4j (`neo4j`)**: The graph database storing the knowledge graph (entities, relations, chunks).
4.  **Redis (`redis`)**: The message broker for the Celery task queue.
5.  **MinIO (`minio`)**: An S3-compatible object storage for the raw uploaded documents.
6.  **SQL Database (SQLite by default)**: A metadata store for tracking document ingestion status and hashes.

![Architecture Diagram (Conceptual)](https://i.imgur.com/example.png)  <!-- Conceptual placeholder -->

---

## Quick Start: Running with Docker

This is the recommended way to run the entire system locally.

### Prerequisites

-   Docker and Docker Compose
-   A `.env` file with your configuration.

### 1. Set up your Environment

Copy the example environment file and fill in your details, especially the API keys and Neo4j password.

```bash
cp .env.example .env
```

**Edit `.env`** with your favorite editor:
- Set a strong `API_SECRET_KEY` (e.g., generate with `openssl rand -hex 32`).
- Set your `OPENAI_API_KEY` or other LLM provider keys.
- Set a `NEO4J_PASSWORD`.

### 2. Build and Run the Services

From the project root (`doublehelix-graphrag/`), run:

```bash
docker-compose -f docker/docker-compose.yml up --build -d
```

This will build the Docker images and start all the required services in the background.

You can monitor the logs:
```bash
docker-compose -f docker/docker-compose.yml logs -f api worker
```

### 3. Interact with the API

The API will be available at `http://localhost:8000`.

---

## API Usage Examples

Replace `YOUR_API_SECRET_KEY` with the key you set in your `.env` file.

### 1. Upload a Document

This kicks off the asynchronous ingestion pipeline.

```bash
curl -X POST "http://localhost:8000/upload" \
     -H "Authorization: Bearer YOUR_API_SECRET_KEY" \
     -F "file=@/path/to/your/document.pdf"
```

**Response (`202 Accepted`):**
```json
{
  "job_id": 1,
  "status": "PENDING",
  "detail": "Document ingestion started."
}
```

### 2. Check Ingestion Status

Use the `job_id` from the upload response.

```bash
curl -X GET "http://localhost:8000/status/1" \
     -H "Authorization: Bearer YOUR_API_SECRET_KEY"
```

**Response (`200 OK`):**
```json
{
  "job_id": 1,
  "filename": "document.pdf",
  "status": "COMPLETED",
  "last_updated": "2025-11-21T10:30:00Z",
  "error": null
}
```

### 3. Query the RAG System

This will stream the response back. The `X-Sources` header contains the context documents used.

```bash
curl -X POST "http://localhost:8000/query?query=What is the main topic of the document?" \
     -H "Authorization: Bearer YOUR_API_SECRET_KEY" \
     --no-buffer -i
```

**Response (`200 OK`):**
```
HTTP/1.1 200 OK
...
X-Sources: [{"document_id": 1, "chunk_id": "...", "score": 0.5}]

The main topic of the document appears to be about advanced retrieval-augmented generation techniques...
```

### 4. Delete a Document

This will remove the document, its chunks, and any orphaned entities from the entire system.

```bash
curl -X DELETE "http://localhost:8000/documents/1" \
     -H "Authorization: Bearer YOUR_API_SECRET_KEY"
```

**Response (`202 Accepted`):**
```json
{
    "job_id": 1,
    "status": "DELETING",
    "detail": "Document deletion process initiated."
}
```

---

## CI/CD with RAG Evaluation

The project includes a GitHub Actions workflow (`.github/workflows/rag-evaluation.yml`) that automatically evaluates the RAG system on every pull request.

-   It spins up the entire application stack using Docker Compose.
-   It runs the `scripts/run_ragas_eval.py` script against the live API.
-   The script evaluates the RAG output against a ground-truth dataset (`tests/evaluation/dataset.json`) using metrics like `faithfulness` and `context_recall`.
-   **If the scores drop below a configurable threshold, the build fails**, preventing merges that degrade quality.

This ensures a continuous, automated quality gate for your RAG system.

```