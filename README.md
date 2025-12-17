# JENEZIS

**Neuro-Symbolic GraphRAG Framework**

**Version 2.0.0** | **License: BSL 1.1**

---

**JENEZIS** is a neuro-symbolic, industrial-grade framework for building advanced knowledge systems. This library moves beyond simple RAG to create a self-learning, auditable, and dynamically configurable reasoning engine.

The core principle is the separation of a **Canonical Store** (the "source of truth") from a **Projection Graph** (the "reasoning engine"), all orchestrated by a neuro-symbolic ingestion pipeline.

## Core Philosophy

- **Symbolic Foundation**: The system's understanding of a domain is not hardcoded. It is defined by a dynamic `DomainConfig` that specifies the allowed entities, relations, and rules. This is the "Symbolic Law" that constrains the "Neuro" (LLM).
- **Canonical First**: All knowledge (entities, aliases) is stored and resolved in a central, canonical store (PostgreSQL with `pgvector`). This prevents data drift and ensures a single source of truth.
- **Graph as a Projection**: The Neo4j graph is a high-performance projection of the canonical data, optimized for complex traversals and reasoning queries. It can be rebuilt from the canonical store at any time.
- **Active Learning Loop**: The system doesn't fail on the unknown; it learns. Unresolved entities are automatically queued for an asynchronous "enrichment" process, allowing the knowledge base to grow and improve with every document ingested.
- **LLM as a Constrained Expert**: Large Language Models are used for what they do best (extraction, summarization) but are strictly governed by the symbolic rules of the `DomainConfig`.

## System Architecture

The architecture is designed for scalability and auditability, with clear data lineage.

1.  **PostgreSQL + pgvector (Canonical Store)**: The foundation. Stores all `DomainConfigs`, `CanonicalNodes` (with their vector embeddings), and `NodeAliases`. This is the system's long-term memory.
2.  **Neo4j (Projection Graph)**: The reasoning layer. Stores a graph of strictly-typed nodes and relationships, projected from the canonical store, enabling multi-hop queries.
3.  **FastAPI App (`api`)**: The main entrypoint, providing REST endpoints for managing domain configs and ingesting documents.
4.  **Celery Workers (`worker`)**:
    - **Ingestion Worker**: Runs the "Harmonizer" pipeline (`Extract -> Resolve -> Validate -> Project`).
    - **Enrichment Worker**: Processes the `enrichment_queue` to learn new entities.
5.  **Redis (`redis`)**: Message broker for Celery.
6.  **MinIO (`minio`)**: S3-compatible object storage for raw documents.

---

## Quick Start: Running with Docker

### 1. Set up your Environment

Copy the environment file. The most critical variable is `INITIAL_ADMIN_KEY`, which you **must** set for the first run.

```bash
cp .env.example .env
```
**Edit `.env`**:
- Set `INITIAL_ADMIN_KEY` to a secure secret. **This will only be used once** to create the first API key.
- Set your `POSTGRES_...` and `NEO4J_PASSWORD`.
- Set your `OPENAI_API_KEY`.

### 2. Build and Run the Services

This command will start all services and automatically apply database migrations via Alembic.

```bash
docker-compose -f docker/docker-compose.yml up --build -d
```
On the first run, the API log will confirm that the initial admin key has been provisioned from your environment variable.

---

## API Usage Examples

Replace `YOUR_API_KEY` with the key you set via `INITIAL_ADMIN_KEY`.

### 1. Define Your "World" (Create a DomainConfig)

First, create a `DomainConfig` to define the types of entities and relationships the system should understand.

```bash
curl -X POST "http://localhost:8000/domain-configs" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "name": "Financial Crime Ontology",
           "schema_json": {
             "entity_types": ["Person", "Company", "Transaction", "Risk"],
             "relationship_types": ["EMPLOYS", "PERFORMS", "HAS_RISK"]
           }
         }'
```
**Response (`201 Created`):**
```json
{
  "name": "Financial Crime Ontology",
  "schema_json": {
    "entity_types": ["Person", "Company", "Transaction", "Risk"],
    "relationship_types": ["EMPLOYS", "PERFORMS", "HAS_RISK"]
  },
  "id": 1
}
```

### 2. Ingest a Document into a Domain

Upload a document and link it to the `DomainConfig` you just created using its `id`.

```bash
curl -X POST "http://localhost:8000/upload?domain_config_id=1" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -F "file=@/path/to/your/financial_report.pdf"
```

**Response (`202 Accepted`):**
```json
{
  "job_id": 1,
  "status": "PENDING",
  "detail": "Document ingestion started."
}
```
The ingestion worker will now process this document *using the rules* defined in the "Financial Crime Ontology".

### 3. Query the System (Reasoning)

Ask a question that requires reasoning over the graph structure.

```bash
curl -X POST "http://localhost:8000/query?query=Which controls mitigate high-priority risks?" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     --no-buffer -i
```

The system will use its LLM planner to translate this into a Cypher query (e.g., `MATCH (r:Risk {priority: 'High'})<-[:MITIGATES]-(c:Control)...`), execute it, and synthesize an answer from the results.

---

## License

JENEZIS is licensed under the **Business Source License 1.1 (BSL 1.1)**.

- **Free for**: Organizations with annual revenue under $100,000, non-commercial use, academic research, and evaluation purposes.
- **Change Date**: December 15, 2029 (converts to Apache 2.0)
- **Commercial licensing**: Contact <jdabert@sigilum.fr>

See [LICENSE](LICENSE) for full details.