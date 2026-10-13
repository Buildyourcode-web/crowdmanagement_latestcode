#!/usr/bin/env bash
# ==============================================================================
# Helper Script to Initialize Database Tables on GPU Instance
# Usage: ./init-db.sh
# ==============================================================================
set -e

echo "==> Running database schema creation and migrations inside byc_gpu_backend container..."
docker exec -it byc_gpu_backend python scripts/init_db.py
docker exec -it byc_gpu_backend alembic upgrade head || true

echo "==> Database schema initialized and migrated successfully!"
echo "==> If you want to seed initial test data/users, you can run:"
echo "    docker exec -it byc_gpu_backend python scripts/seed.py"

