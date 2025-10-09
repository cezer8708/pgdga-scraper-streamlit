#!/bin/bash
# 1. Set the installation directory to be within the Streamlit app's environment
# The location $PWD/browser_cache is always accessible inside the Streamlit container.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 2. Run the install command with system dependencies
python -m playwright install --with-deps chromium