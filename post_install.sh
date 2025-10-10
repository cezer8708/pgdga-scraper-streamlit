#!/bin/bash

# 1. CRITICAL: Activate the Python Virtual Environment (venv).
# This ensures that the 'python -m playwright' command runs within the environment
# where Playwright was installed by Streamlit's pip process.
source /app/venv/bin/activate

# 2. CRITICAL: Set the installation directory to be within the Streamlit app's environment.
# This variable tells Playwright where to download the browser executable.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 3. Run the install command for Chromium using the custom path defined above.
# We explicitly call 'python -m playwright' as a more robust way to execute the install command.
# The '--with-deps' flag is essential for ensuring all necessary system libraries are included.
python -m playwright install --with-deps chromium
