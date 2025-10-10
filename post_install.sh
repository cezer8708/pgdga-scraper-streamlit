#!/bin/bash

# 1. Set the custom browser installation directory.
# This variable directs Playwright where to save the browser executables.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 2. Execute the installation using the most explicit, absolute path expected
# on the Streamlit Cloud server.
/home/appuser/venv/bin/playwright install --with-deps chromium