"""
This test module can be used to integrate the Ragas evaluation script
into a pytest run, although the script is primarily designed to be
run standalone in a CI environment.
"""
import subprocess
import sys
import os
import pytest

# Mark this test as 'evaluation' to allow selective runs with `pytest -m evaluation`
@pytest.mark.evaluation
def test_ragas_evaluation_script():
    """
    Runs the run_ragas_eval.py script as a subprocess.
    This test will fail if the script exits with a non-zero status code.
    
    It requires the full application stack to be running (e.g., via docker-compose).
    The necessary environment variables (API_URL, API_SECRET_KEY, etc.) must be set.
    """
    script_path = os.path.join(
        os.path.dirname(__file__),
        '..', '..', 'scripts', 'run_ragas_eval.py'
    )
    
    # Ensure the script path is valid
    if not os.path.exists(script_path):
        pytest.fail(f"Evaluation script not found at: {script_path}")

    # The script requires environment variables like API_SECRET_KEY, which should
    # be set in the CI environment.
    if "API_SECRET_KEY" not in os.environ:
        pytest.skip("Skipping Ragas evaluation test: API_SECRET_KEY not set.")

    try:
        # We use subprocess.run to execute the script and capture its output.
        # check=True will raise a CalledProcessError if the script returns a non-zero exit code.
        result = subprocess.run(
            [sys.executable, script_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5-minute timeout
        )
        # If the script succeeds, print its output for logging purposes.
        print("Ragas evaluation script stdout:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        # If the script fails, pytest will fail this test and print the script's
        # stdout and stderr, which is useful for debugging in CI logs.
        pytest.fail(
            f"Ragas evaluation script failed with exit code {e.returncode}.\n"
            f"--- STDOUT ---\n{e.stdout}\n"
            f"--- STDERR ---\n{e.stderr}"
        )
    except subprocess.TimeoutExpired as e:
        pytest.fail(
             f"Ragas evaluation script timed out after {e.timeout} seconds.\n"
            f"--- STDOUT ---\n{e.stdout}\n"
            f"--- STDERR ---\n{e.stderr}"
        )
