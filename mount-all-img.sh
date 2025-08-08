#!/bin/bash
# Wrapper script that calls the Python implementation
exec python3 "$(dirname "$0")/mount-all-img.py" "$@"