"""
Locust Load Tests for JENEZISGraphRAG

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Or headless:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
        --users=100 --spawn-rate=10 --run-time=5m --headless

Scenarios:
- Stress test: 100 users, spawn rate 10/s, 5min duration
- Spike test: 0->200 users in 30s, hold 2min
- Endurance: 50 users constant for 30min
"""
import os
import random
import hashlib
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


# Configuration from environment
API_KEY = os.environ.get("API_SECRET_KEY", "test-api-key")
ONTOLOGY_ID = os.environ.get("TEST_ONTOLOGY_ID", "1")


class JENEZISUser(HttpUser):
    """
    Simulates a typical user interacting with the JENEZIS API.

    Task weights represent relative frequency:
    - query_rag (3): Most common operation
    - check_status (2): Frequent status checks
    - upload_document (1): Less frequent uploads
    """

    wait_time = between(0.5, 2.0)  # 0.5-2 seconds between requests
    headers = {"Authorization": f"Bearer {API_KEY}"}

    def on_start(self):
        """Called when a user starts. Can be used for setup."""
        self.document_ids = []

    @task(3)
    def query_rag(self):
        """
        Send a RAG query - the most common operation.
        """
        queries = [
            "What controls mitigate financial risks?",
            "Who works at Acme Corporation?",
            "List all identified risks in the system.",
            "What are the relationships between entities?",
            "Show me high priority items.",
        ]

        query = random.choice(queries)

        with self.client.post(
            "/query",
            params={"query": query},
            headers=self.headers,
            catch_response=True,
            stream=True,  # Handle streaming response
        ) as response:
            if response.status_code == 200:
                # Read the streaming response
                content = b""
                for chunk in response.iter_content(chunk_size=1024):
                    content += chunk
                response.success()
            elif response.status_code == 403:
                response.failure("Authentication failed")
            else:
                response.failure(f"Query failed: {response.status_code}")

    @task(2)
    def check_status(self):
        """
        Check document status - frequent operation during processing.
        """
        # Check a random document ID or use a known one
        doc_id = random.choice(self.document_ids) if self.document_ids else 1

        with self.client.get(
            f"/status/{doc_id}",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            elif response.status_code == 403:
                response.failure("Authentication failed")
            else:
                response.failure(f"Status check failed: {response.status_code}")

    @task(1)
    def upload_document(self):
        """
        Upload a small document - less frequent but resource intensive.
        """
        # Generate unique content
        content = f"Test document {random.randint(1, 1000000)}. ".encode()
        content += b"John Doe works for Acme Corporation. "
        content += b"Financial Risk identified. Compliance Control mitigates risk."

        file_hash = hashlib.sha256(content).hexdigest()[:8]
        filename = f"loadtest_{file_hash}.txt"

        with self.client.post(
            f"/upload?ontology_id={ONTOLOGY_ID}",
            files={"file": (filename, content, "text/plain")},
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                data = response.json()
                if "job_id" in data:
                    self.document_ids.append(data["job_id"])
                    # Keep only last 10 IDs to avoid memory growth
                    self.document_ids = self.document_ids[-10:]
                response.success()
            elif response.status_code == 409:
                # Duplicate - expected under high load
                response.success()
            elif response.status_code == 403:
                response.failure("Authentication failed")
            else:
                response.failure(f"Upload failed: {response.status_code}")

    @task(1)
    def list_ontologies(self):
        """
        List ontologies - lightweight operation for baseline.
        """
        with self.client.get(
            "/ontologies",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 403:
                response.failure("Authentication failed")
            else:
                response.failure(f"List failed: {response.status_code}")


class QueryOnlyUser(HttpUser):
    """
    User that only performs queries - for testing query performance.
    """

    wait_time = between(0.1, 0.5)  # More aggressive
    headers = {"Authorization": f"Bearer {API_KEY}"}

    @task
    def query_rag(self):
        """Send RAG queries rapidly."""
        queries = [
            "What are the risks?",
            "Show controls.",
            "List entities.",
        ]

        with self.client.post(
            "/query",
            params={"query": random.choice(queries)},
            headers=self.headers,
            catch_response=True,
            stream=True,
        ) as response:
            if response.status_code == 200:
                for _ in response.iter_content(chunk_size=1024):
                    pass
                response.success()
            else:
                response.failure(f"Query failed: {response.status_code}")


class UploadHeavyUser(HttpUser):
    """
    User that primarily uploads documents - for testing ingestion capacity.
    """

    wait_time = between(1, 3)
    headers = {"Authorization": f"Bearer {API_KEY}"}

    @task(5)
    def upload_document(self):
        """Upload documents heavily."""
        content = f"Heavy upload test {random.randint(1, 10000000)}. ".encode()
        content += b"Test entity. Another entity. " * 100

        filename = f"heavy_{random.randint(1, 10000000)}.txt"

        with self.client.post(
            f"/upload?ontology_id={ONTOLOGY_ID}",
            files={"file": (filename, content, "text/plain")},
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code in [202, 409]:
                response.success()
            else:
                response.failure(f"Upload failed: {response.status_code}")

    @task(1)
    def check_status(self):
        """Occasional status check."""
        with self.client.get(
            "/status/1",
            headers=self.headers,
            catch_response=True,
        ) as response:
            response.success()


# Event handlers for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    if isinstance(environment.runner, MasterRunner):
        print("Load test starting on master node")
    else:
        print("Load test starting")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("\n=== Load Test Summary ===")
    if environment.stats.total:
        total = environment.stats.total
        print(f"Total requests: {total.num_requests}")
        print(f"Failed requests: {total.num_failures}")
        print(f"Avg response time: {total.avg_response_time:.2f}ms")
        print(f"Median response time: {total.median_response_time:.2f}ms")
        print(f"95th percentile: {total.get_response_time_percentile(0.95):.2f}ms")
        print(f"99th percentile: {total.get_response_time_percentile(0.99):.2f}ms")
        print(f"Requests/sec: {total.total_rps:.2f}")
