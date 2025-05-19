#!/bin/bash
# Test script for Claude Explain server (local or deployed)
# Usage: ./test-explain.sh [url]
# Options:
#   -p, --pretty    Format the JSON output nicely (requires jq)
#   -u, --url URL   Full URL to the explain endpoint

# Parse options
PRETTY=0
URL=""
while [[ "$#" -gt 0 ]]; do
  case $1 in
    -p|--pretty) PRETTY=1; shift ;;
    -u|--url) URL="$2"; shift 2 ;;
    *)
      # First positional parameter is the URL
      if [[ "$URL" == "" ]]; then
        URL="$1"
      fi
      shift ;;
  esac
done

# Default URL if nothing was provided
URL=${URL:-http://localhost:8080/explain}

echo "Testing Claude Explain server at $URL"

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
  curl -s -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD" | jq '.'
else
  echo "Using raw output format"
  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD"
fi

# Add a newline for better formatting
echo ""
