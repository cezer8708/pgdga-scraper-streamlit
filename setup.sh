# Install necessary system dependencies for Playwright (Chromium)
# The following libraries are often required for Playwright to run headless browsers on Streamlit's Linux environment.
# Note: --no-install-recommends makes the install faster and smaller.
apt-get update
apt-get install -y --no-install-recommends \
    libnss3 \
    libgtk-3-0 \
    libgconf-2-4 \
    libasound2 \
    libgbm1 \
    libxtst6

# Install the Playwright browser drivers (Chromium, Firefox, WebKit)
playwright install --with-deps