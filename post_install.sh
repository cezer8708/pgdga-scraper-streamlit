#!/bin/bash

# 1. Set the installation directory to be within the Streamlit app's environment.
# This variable tells Playwright where to download the browser executable.
export PLAYWRIGHT_BROWSERS_PATH=$PWD/browser_cache

# 2. Run the install command for Chromium.
# '--with-deps' ensures all necessary system libraries are included for the browser.
playwright install --with-deps chromium