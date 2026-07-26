#!/usr/bin/env sh
# Run the whole test suite (including the Home Assistant tests) in Docker.
#
# Home Assistant's runner imports the POSIX-only `fcntl`, so
# pytest-homeassistant-custom-component cannot run on Windows natively — the
# HA-dependent modules just skip themselves there and only the pure suite runs.
# This container gives the same Linux + Python 3.14 environment as CI.
#
#   sh scripts/run-tests.sh                 # everything
#   sh scripts/run-tests.sh tests/test_actions.py -q
#
# Rebuild the image after changing requirements-test.txt.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=rf-fan-tests

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building $IMAGE ..."
    docker build -q -f "$REPO/scripts/Dockerfile.tests" -t "$IMAGE" "$REPO"
fi

if [ "$#" -eq 0 ]; then
    set -- python -m pytest tests/ -q
else
    set -- python -m pytest "$@"
fi

exec docker run --rm -v "$REPO:/app" -w /app "$IMAGE" "$@"
