#!/bin/bash

# 1. Install necessary system dependencies for Playwright (Chromium)
# These Linux libraries are required for headless Chromium to run.
# This part is based on your setup.sh file content.
apt-get update
apt-get install -y --no-install-recommends \
    libnss3 \
    libxss1 \
    libgtk-3-0 \
    libgconf-2-4 \
    libasound2 \
    libgbm1 \
    libxtst6

# 2. Set the custom browser installation directory.
# This variable directs Playwright where to save the browser executables.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 3. Install the Playwright browser drivers into the custom path.
# We use the standard 'python -m' command here, which is often stable when
# the system dependencies (Step 1) are guaranteed to be present.
python -m playwright install --with-deps chromium