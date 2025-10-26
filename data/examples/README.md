# Examples Directory

This directory contains example data files for testing and demonstration purposes.

## Files

### cv_example.json
- **Purpose:** Example CV data structure for testing the ingestion pipeline
- **Content:** Fictional candidate "John Doe" with complete profile
- **Usage:** Used by `src/graph_ingestion/ingest.py` as default input
- **Format:** JSON structure expected by the CV parsing pipeline

## How to Use

1. **Testing the pipeline:**
   ```bash
   poetry run python src/graph_ingestion/ingest.py
   ```

2. **Using your own CV data:**
   - Copy your CV JSON file to this directory
   - Update `PARSED_CV_FILE` in `src/graph_ingestion/ingest.py`
   - Or pass the file path as a command-line argument

3. **Output:**
   - Generated Cypher queries will be saved to `data/output/cypher_queries.txt`
   - Load into Neo4j: `cypher-shell < data/output/cypher_queries.txt`

## Data Structure

The CV JSON should follow this structure:
- `documents[].parsed_data.extracted_data.profile`
- `documents[].parsed_data.extracted_data.experiences`
- `documents[].parsed_data.extracted_data.education`
- `documents[].parsed_data.extracted_data.skills`

See `cv_example.json` for complete schema reference.