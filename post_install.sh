#!/bin/bash

# 1. CRITICAL: Set the installation directory to be within the Streamlit app's environment.
# This variable tells Playwright where to download the browser executable ($PWD is the current working directory).
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 2. Run the install command for Chromium using the custom path defined above.
# We explicitly call 'python -m playwright' as a more robust way to execute the install command.
# The '--with-deps' flag is essential for ensuring all necessary system libraries are included.
python -m playwright install --with-deps chromium