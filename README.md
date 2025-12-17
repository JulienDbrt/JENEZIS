# JENEZIS

**Neuro-Symbolic GraphRAG Framework**

**Version 2.0.0** | **License: BSL 1.1**

![Tests](https://img.shields.io/badge/tests-237%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-80%25+-blue)
![Security](https://img.shields.io/badge/security-adversarial%20tested-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)

---

**JENEZIS** is a neuro-symbolic, industrial-grade framework for building advanced knowledge systems. It moves beyond simple RAG to create a self-learning, auditable, and dynamically configurable reasoning engine.

The core principle is the separation of a **Canonical Store** (the "source of truth") from a **Projection Graph** (the "reasoning engine"), all orchestrated by a neuro-symbolic ingestion pipeline.

## Why JENEZIS?

| Classic RAG | JENEZIS |
|-------------|---------|
| Vector similarity only | **Hybrid retrieval**: vector + LLM-planned Cypher + Reciprocal Rank Fusion |
| Entity drift over time | **Canonical resolution**: every mention → unique canonical node |
| No schema enforcement | **Dynamic ontology**: DomainConfig constrains extraction |
| Unknown entities fail | **Active learning**: enrichment queue learns new entities |
| Flat document chunks | **Multi-hop reasoning**: Neo4j graph traversals |
| Minimal security | **Adversarial-tested**: injection, traversal, DoS, race conditions |

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

## Security & Production Readiness

Built for environments where reliability and auditability are non-negotiable.

- **Input sanitization**: Path traversal, null bytes, protocol injection blocked at upload
- **Cypher injection prevention**: Dynamic labels/relations validated against strict patterns
- **Prompt injection hardening**: Ontology schemas and retriever outputs sanitized
- **State machine enforcement**: Invalid document status transitions rejected
- **Adversarial test suite**: 237 tests including injection, race conditions, DoS vectors
- **Docker secrets**: No credentials in environment variables or logs
- **Structured logging**: JSON output for SIEM integration

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

## Use Cases

JENEZIS excels where **factual precision**, **traceability**, and **long-term maintenance** matter more than raw speed.

| Domain | Why JENEZIS Fits |
|--------|------------------|
| **Financial Crime / AML** | Ontology-constrained extraction (Person, Company, Transaction). Multi-hop queries ("Who transacted with flagged entities?"). Full audit trail for regulators. |
| **Competitive Intelligence** | Documents evolve constantly. Canonical store prevents data ghosts. Document deletion cascades cleanly with garbage collection. |
| **Enterprise Risk Management** | Model Risk → Control → Mitigation relationships. Hybrid retrieval answers "Which controls mitigate priority risks?" with graph precision. |
| **M&A Due Diligence / KYC** | Hundreds of heterogeneous documents. Resolver merges aliases ("Tesla Inc", "TSLA", "Tesla Motors") into single canonical nodes. |
| **Regulated Systems (Finance, Health, Defense)** | Full traceability (status, job_id, error_log). Rebuild graph from canonical store for audit. State machine prevents invalid transitions. |
| **Digital Twin / Network Infrastructure** | Model complex topologies (servers, switches, dependencies). Real-time IoT ingestion via async workers. Risk/vulnerability chain analysis with zero hallucinations. |

## Comparison with Alternatives

How JENEZIS compares to other GraphRAG approaches for knowledge-intensive applications.

| Capability | JENEZIS | Microsoft GraphRAG | Pure Graph DB (e.g., TigerGraph) |
|------------|---------|--------------------|---------------------------------|
| **Entity Resolution** | Neuro-symbolic resolver (exact → vector → enrichment) ensures single canonical node per entity | Name-based only; duplicates possible in evolving datasets | Manual or rule-based; no LLM-assisted resolution |
| **Schema Enforcement** | Dynamic ontology (DomainConfig) constrains LLM extraction | No strict schema; entities/relations inferred | Strong schema but no LLM constraint |
| **Incremental Updates** | Async ingestion + garbage collection; no full reindex | Expensive reindexing (LazyGraphRAG improves to ~4% cost) | Native streaming; excellent for high-velocity data |
| **Audit & Rebuild** | Canonical Store is source of truth; graph rebuildable anytime | Index is derived artifact; not designed for audit | Query logs available but no canonical separation |
| **Hallucination Control** | Symbolic validation + prompt sanitization + adversarial tests | Community summaries may propagate errors | No LLM layer; pure graph queries |
| **Best For** | Precision-critical, auditable, evolving knowledge bases | Global queries over large text corpora | Massive real-time graph analytics |

*References: [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) (GraphRAG), [arXiv:2412.07189](https://arxiv.org/abs/2412.07189) (GraphRAG in wireless networks), Microsoft Research 2025 (LazyGraphRAG), IOWN Global Forum (Network Digital Twin standards).*

---

## License

JENEZIS is licensed under the **Business Source License 1.1 (BSL 1.1)**.

- **Free for**: Organizations with annual revenue under $100,000, non-commercial use, academic research, and evaluation purposes.
- **Change Date**: December 15, 2029 (converts to Apache 2.0)
- **Commercial licensing**: Contact <jdabert@sigilum.fr>

See [LICENSE](LICENSE) for full details.