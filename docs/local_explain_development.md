# Local Development for Claude Explain Service

This document outlines how to run and test the Claude Explain service locally during development.

## Local HTTP Server Mode

The `explain.py` script includes a built-in HTTP server for local development, allowing you to test changes to the prompt, model parameters, and processing logic without deploying to AWS.

### Prerequisites

1. [Anthropic API key](https://console.anthropic.com/settings/keys)
2. Python 3.9+ with the required dependencies installed

### Setting Up Your API Key

For security reasons, your Claude API key should be stored in a file. The script will automatically look for a file named `.claude-explain-key` in the current directory.

To set up your API key:

```bash
cd lambda
echo "your_claude_api_key_here" > .claude-explain-key
chmod 600 .claude-explain-key  # Restrict permissions for added security
```

This file is automatically excluded from git to prevent accidentally committing your API key.

### Running the Local Server

Once you've set up your API key, you can run the local server:

```bash
cd lambda
python explain.py --server
```

This will start a local HTTP server on `localhost:8080` that responds to POST requests at the `/explain` endpoint.

### Command Line Options

The local server supports several command line options:

```
--server              Run in local server mode
--host HOSTNAME       Host for local server (default: localhost)
--port PORT           Port for local server (default: 8080)
--api-key-file PATH   Path to file containing Claude API key (default: .claude-explain-key)
--model MODEL         Claude model to use (default: claude-3-haiku-20240307)
--max-tokens TOKENS   Maximum tokens for the explanation (default: 1024)
```

Examples:

```bash
# Run on a different port
python explain.py --server --port 9000

# Use a custom API key file
python explain.py --server --api-key-file my-api-keys/claude-key.txt

# Use a different Claude model
python explain.py --server --model claude-3-sonnet-20240229

# Increase the max tokens for longer explanations
python explain.py --server --max-tokens 2048
```

## Testing with curl

Once the server is running, you can test it using curl:

```bash
curl -X POST http://localhost:8080/explain \
  -H "Content-Type: application/json" \
  -d '{
    "language": "c++",
    "compiler": "g++",
    "code": "int square(int x) { return x * x; }",
    "compilationOptions": ["-O2"],
    "instructionSet": "amd64",
    "asm": [
      {
        "text": "square(int):",
        "source": null,
        "labels": []
      },
      {
        "text": "        mov     eax, edi",
        "source": {
          "line": 1,
          "column": 21
        },
        "labels": []
      },
      {
        "text": "        imul    eax, edi",
        "source": {
          "line": 2,
          "column": 10
        },
        "labels": []
      },
      {
        "text": "        ret",
        "source": {
          "line": 2,
          "column": 10
        },
        "labels": []
      }
    ],
    "labelDefinitions": {
      "square(int)": 0
    }
  }'
```

### Response Format

The service returns a JSON response with the following structure:

```json
{
  "explanation": "This assembly implements the square function...",
  "status": "success",
  "model": "claude-3-haiku-20240307",
  "usage": {
    "input_tokens": 123,
    "output_tokens": 456,
    "total_tokens": 579
  },
  "cost": {
    "input_cost": 0.000123,
    "output_cost": 0.000456,
    "total_cost": 0.000579
  }
}
```

The response includes:

- **explanation**: The explanation of the assembly code
- **model**: The Claude model used for generation
- **usage**: Token usage statistics
- **cost**: Estimated cost of the API call in USD

## Iterating on the System Prompt

The primary use case for local development is to iterate on the system prompt to optimize Claude's explanations. To modify the prompt:

1. Open `lambda/explain.py` and locate the `process_request` function
2. Modify the `system_prompt` variable with your new prompt text
3. Restart the local server to test your changes

Example:

```python
# System prompt - can be customized for iterating on prompts locally
system_prompt = """You are an expert compiler analyst who explains the relationship between source code and assembly output.
Provide clear, concise explanations that help programmers understand how their code translates to assembly.
Focus on key transformations, optimizations, and important assembly patterns.
Format your explanation with markdown for better readability.
Start with a high-level overview followed by line-by-line analysis.
"""
```

## Testing with Compiler Explorer

If you're running Compiler Explorer locally, you can configure it to use your local Claude Explain service:

1. In your CE configuration file (e.g., `etc/config/compiler-explorer.local.properties`), add:
   ```
   explanationUrl=http://localhost:8080/explain
   ```

2. Add a new button to the CE UI to call the explain service by modifying the appropriate UI configuration.

## Debugging Tips

1. The server logs all requests and any errors to the console
2. You can use `print()` statements in the code for additional debugging
3. For detailed HTTP tracing, use the `-v` flag with curl:
   ```bash
   curl -v -X POST http://localhost:8080/explain -H "Content-Type: application/json" -d '...'
   ```

## Additional Development Notes

### Security Best Practices

1. **API Key Storage**:
   - Store your API key in a file with restricted permissions (`chmod 600 .claude-explain-key`)
   - Ensure the key file is included in `.gitignore` to prevent accidental commits
   - Never share or commit your API key

2. **Local Network Binding**:
   - By default, the server binds to `localhost` only, which is the most secure option
   - Only use other host bindings (like `0.0.0.0`) if you need to access the server from other machines

### Modifying the API

If you need to change the API format or parameters:

1. Update the `validate_input` function for any new or changed fields
2. Modify the `prepare_structured_data` function to process these fields
3. Update the tests in `explain_test.py`

### Testing Different Claude Models

You can test with different Claude models by using the `--model` flag:

```bash
python explain.py --server --model claude-3-sonnet-20240229
```

### Comparing Explanations

To compare explanations between different prompts or models, you can save the outputs to files:

```bash
curl -X POST http://localhost:8080/explain -H "Content-Type: application/json" -d @test_input.json > response1.json
# Make changes to prompt
curl -X POST http://localhost:8080/explain -H "Content-Type: application/json" -d @test_input.json > response2.json
diff response1.json response2.json
```
