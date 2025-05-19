#!/bin/bash
# Test script for local Claude Explain server
# Usage: ./test-explain.sh [host] [port]
# Options:
#   -p, --pretty    Format the JSON output nicely (requires jq)

# Parse options
PRETTY=0
HOST=""
PORT=""
while [[ "$#" -gt 0 ]]; do
  case $1 in
    -p|--pretty) PRETTY=1; shift ;;
    *)
      if [[ "$HOST" == "" ]]; then
        HOST="$1"
      elif [[ "$PORT" == "" ]]; then
        PORT="$1"
      fi
      shift ;;
  esac
done

# Default host and port
HOST=${HOST:-localhost}
PORT=${PORT:-8080}

echo "Testing Claude Explain server at http://$HOST:$PORT/explain"

# Prepare the JSON payload
JSON_PAYLOAD=$(cat <<'EOF'
{
  "language": "c++",
  "compiler": "g++",
  "code": "int factorial(int n) {\n  if (n <= 1) return 1;\n  return n * factorial(n-1);\n}",
  "compilationOptions": ["-O2"],
  "instructionSet": "amd64",
  "asm": [
    {
      "text": "factorial(int):",
      "source": null,
      "labels": []
    },
    {
      "text": "        cmp     edi, 1",
      "source": {
        "line": 2,
        "column": 6
      },
      "labels": []
    },
    {
      "text": "        jle     .L4",
      "source": {
        "line": 2,
        "column": 6
      },
      "labels": [
        {"name": ".L4", "range": {"startCol": 13, "endCol": 16}}
      ]
    },
    {
      "text": "        push    rbx",
      "source": {
        "line": 3,
        "column": 9
      },
      "labels": []
    },
    {
      "text": "        mov     ebx, edi",
      "source": {
        "line": 3,
        "column": 9
      },
      "labels": []
    },
    {
      "text": "        lea     edi, [rdi-1]",
      "source": {
        "line": 3,
        "column": 19
      },
      "labels": []
    },
    {
      "text": "        call    factorial(int)",
      "source": {
        "line": 3,
        "column": 19
      },
      "labels": [
        {"name": "factorial(int)", "range": {"startCol": 13, "endCol": 27}}
      ]
    },
    {
      "text": "        imul    eax, ebx",
      "source": {
        "line": 3,
        "column": 9
      },
      "labels": []
    },
    {
      "text": "        pop     rbx",
      "source": {
        "line": 3,
        "column": 9
      },
      "labels": []
    },
    {
      "text": "        ret",
      "source": {
        "line": 3,
        "column": 9
      },
      "labels": []
    },
    {
      "text": ".L4:",
      "source": null,
      "labels": []
    },
    {
      "text": "        mov     eax, 1",
      "source": {
        "line": 2,
        "column": 18
      },
      "labels": []
    },
    {
      "text": "        ret",
      "source": {
        "line": 2,
        "column": 18
      },
      "labels": []
    }
  ],
  "labelDefinitions": {
    "factorial(int)": 0,
    ".L4": 10
  }
}
EOF
)

# Send the request using curl with the JSON payload
if [[ $PRETTY -eq 1 ]]; then
  echo "Using pretty output format (jq)"
  curl -s -X POST "http://$HOST:$PORT/explain" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" | jq '.'
else
  echo "Using raw output format"
  curl -X POST "http://$HOST:$PORT/explain" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD"
fi

# Add a newline for better formatting
echo ""
