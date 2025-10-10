#!/bin/bash

# 1. CRITICAL: Set the custom browser installation directory.
# This variable directs Playwright to save the browser executables here.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 2. Execute the installation directly using the expected executable path.
# This bypasses issues with 'source activate' and 'python -m playwright'.
# This command assumes the virtual environment is named 'venv'. If your environment
# is named differently (e.g., 'env'), you may need to adjust the path.
./venv/bin/playwright install --with-deps chromium