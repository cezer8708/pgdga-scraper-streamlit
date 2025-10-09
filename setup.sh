# Install necessary system dependencies for Playwright (Chromium)
apt-get update
apt-get install -y libnss3 libatk-bridge2.0-0 libgtk-3-0 libgconf-2-4 libasound2 libdrm2 libgbm1
# Install the Playwright browser drivers (Chromium, Firefox, WebKit)
playwright install --with-deps