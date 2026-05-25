#!/usr/bin/env bash
# Build and tag the CTFacile SQLi challenge image.
# Run this from the project root OR from challenge_images/sqli-login/.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="ctfacile/sqli-base:latest"

echo "→ Building $IMAGE_TAG ..."
docker build -t "$IMAGE_TAG" "$SCRIPT_DIR"
echo "✓ Image built: $IMAGE_TAG"

echo ""
echo "→ Quick smoke-test (starts container, checks HTTP 200 on /, then removes it)..."
CID=$(docker run -d --rm -p 15000:80 -e FLAG="FLAG{test_ok}" "$IMAGE_TAG")
sleep 2
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:15000/)
docker stop "$CID" > /dev/null
if [ "$STATUS" = "200" ]; then
    echo "✓ Smoke test passed (HTTP $STATUS)"
else
    echo "✗ Smoke test FAILED (HTTP $STATUS)" && exit 1
fi

echo ""
echo "Done. The image is ready. Run the Django management command next:"
echo "  docker compose exec web python manage.py patch_sqli_image"
