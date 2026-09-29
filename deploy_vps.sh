#!/bin/bash
# One-command automated VPS deployment for Crypto Trade Agent
set -e

echo "=== Deploying Crypto Trade Agent on VPS ==="

# 1. Update and install Docker if missing
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    systemctl enable docker
    systemctl start docker
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    apt-get update && apt-get install -y docker-compose-plugin docker-compose
fi

# 2. Check for .env file
if [ ! -f .env ]; then
    echo "WARNING: .env not found. Copying .env.example if available..."
    if [ -f .env.example ]; then
        cp .env.example .env
    fi
fi

# 3. Create persistent data directory
mkdir -p data

# 4. Build and start containers
echo "Building and launching containerized supervisor and workstation..."
docker-compose down || true
docker-compose build
docker-compose up -d

echo "=== Deployment Complete ==="
echo "Workstation running on: http://$(curl -s ifconfig.me):8000"
echo "Check logs: docker-compose logs -f"
