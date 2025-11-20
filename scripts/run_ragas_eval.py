"""
Script for running RAG evaluation using Ragas.
This script is designed to be called from a CI/CD pipeline.
It queries a running instance of the DoubleHelix API, evaluates the
responses against a ground truth dataset, and exits with a status code
indicating success or failure based on performance thresholds.
"""
import os
import sys
import json
import asyncio
import logging

import httpx
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_recall

# --- Configuration ---
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_SECRET_KEY")
DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")

# Get thresholds from environment or use defaults
FAITHFULNESS_THRESHOLD = float(os.getenv("RAGAS_FAITHFULNESS_THRESHOLD", 0.85))
CONTEXT_RECALL_THRESHOLD = float(os.getenv("RAGAS_CONTEXT_RECALL_THRESHOLD", 0.80))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def run_evaluation():
    """Main function to run the RAGAS evaluation."""
    if not API_KEY:
        logging.error("API_SECRET_KEY environment variable not set.")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {API_KEY}"}

    # 1. Load evaluation dataset from JSON file
    with open(DATASET_PATH, 'r') as f:
        eval_data = json.load(f)
    
    questions = [item['question'] for item in eval_data]
    ground_truths = [item['ground_truth'] for item in eval_data]

    # 2. Query the RAG system for each question to get answers and contexts
    answers = []
    contexts = []
    async with httpx.AsyncClient(timeout=120) as client:
        for q in questions:
            try:
                logging.info(f"Querying API for question: '{q}'")
                response = await client.post(f"{API_URL}/query", params={"query": q}, headers=headers)
                response.raise_for_status()

                # The answer is the streaming content
                answer_text = response.text
                answers.append(answer_text)

                # The contexts are in the 'X-Sources' header
                sources_json = response.headers.get("X-Sources", "[]")
                retrieved_sources = json.loads(sources_json)
                # Ragas expects a list of lists of strings
                contexts.append([source['text'] for source in retrieved_sources if 'text' in source])
                logging.info(f"Received answer and {len(retrieved_sources)} sources.")

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logging.error(f"API request failed for question '{q}': {e}")
                answers.append("")
                contexts.append([])

    # 3. Prepare dataset for Ragas
    dataset_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    }
    dataset = Dataset.from_dict(dataset_dict)

    # 4. Run Ragas evaluation
    logging.info("Starting Ragas evaluation...")
    metrics = [faithfulness, answer_relevancy, context_recall]
    result = evaluate(dataset, metrics=metrics)
    logging.info("Ragas evaluation completed.")
    
    # 5. Check results against thresholds
    scores = result.to_pandas()
    logging.info("\n" + scores.to_string())

    avg_faithfulness = scores['faithfulness'].mean()
    avg_context_recall = scores['context_recall'].mean()
    
    logging.info(f"\n--- Evaluation Summary ---")
    logging.info(f"Average Faithfulness: {avg_faithfulness:.2f} (Threshold: {FAITHFULNESS_THRESHOLD:.2f})")
    logging.info(f"Average Context Recall: {avg_context_recall:.2f} (Threshold: {CONTEXT_RECALL_THRESHOLD:.2f})")

    # 6. Exit with status code
    if avg_faithfulness < FAITHFULNESS_THRESHOLD or avg_context_recall < CONTEXT_RECALL_THRESHOLD:
        logging.error("Evaluation FAILED: One or more metrics are below the threshold.")
        sys.exit(1)
    else:
        logging.info("Evaluation PASSED: All metrics meet or exceed thresholds.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
