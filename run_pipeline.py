import subprocess
import sys
import logging

import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def run_script(script_name):
    logging.info(f"Running {script_name}...")
    result = subprocess.run([sys.executable, script_name], capture_output=True, text=True)
    if result.returncode != 0:
        logging.error(f"Error running {script_name}:\n{result.stderr}")
        sys.exit(result.returncode)
    else:
        logging.info(f"{script_name} completed successfully.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

def main():
    logging.info("Starting AI Tools Newsletter Pipeline")
    start_time = time.time()
    run_script("fetch_sources.py")
    run_script("curate.py")
    run_script("build_draft.py")
    end_time = time.time()
    logging.info(f"Pipeline completed successfully. Runtime: {end_time - start_time:.1f} s")

if __name__ == "__main__":
    main()
