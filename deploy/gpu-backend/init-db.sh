#!/usr/bin/env bash
# ==============================================================================
# Helper Script to Initialize Database Tables on GPU Instance
# Usage: ./init-db.sh
# ==============================================================================
set -e

echo "==> Running database schema creation inside byc_gpu_backend container..."
docker exec -it byc_gpu_backend python scripts/init_db.py

echo "==> Database schema initialized successfully!"
echo "==> If you want to seed initial test data/users, you can run:"
echo "    docker exec -it byc_gpu_backend python scripts/seed.py"
