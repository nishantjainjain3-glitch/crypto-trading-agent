#!/usr/bin/env bash
# One-click deployment script for Linux VPS (Ubuntu/Debian)
set -e

echo "=== Deploying Crypto Trading Agent 24/7 Service ==="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[+] Installing Docker and Docker Compose..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm -f get-docker.sh
fi

# Ensure .env exists
if [ ! -f .env ]; then
    echo "[!] .env not found. Please create .env with your Binance API keys before launching."
    exit 1
fi

# Build and start container
echo "[+] Starting autonomous container..."
docker compose down || true
docker compose up --build -d

echo "[+] Deployment successful!"
echo "[+] Web dashboard running at: http://$(curl -s ifconfig.me):8000"
echo "[+] Streaming logs: docker compose logs -f"
