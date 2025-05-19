# Claude Explain Service Design Document

## Overview

The Claude Explain service will provide AI-powered explanations of compiler output for Compiler Explorer users. This service will receive compiled code and its resulting assembly, then use Claude Haiku to generate explanations that help users understand the relationship between their source code and the generated assembly.

## Architecture

### Service Components

1. **Lambda Function**: A Python-based AWS Lambda function that will:
   - Receive requests through API Gateway
   - Validate input data
   - Process and prepare structured JSON for Claude
   - Call Claude Haiku with the structured data
   - Return Claude's response to the client

2. **API Gateway**: HTTP API Gateway to:
   - Expose the `/explain` endpoint
   - Handle request routing
   - Provide CORS support
   - Enable rate limiting

3. **Infrastructure**: Terraform configuration to:
   - Define the lambda function with appropriate permissions
   - Configure API Gateway routes and integrations
   - Set up CloudWatch logging
   - Implement rate limiting and security measures

### Input Format

The service will accept POST requests with JSON bodies containing a subset of the Compiler Explorer API's `/api/compiler/<compiler-id>/compile` response, focusing on the most relevant information for assembly explanation:

```json
{
  "language": "string",               // Programming language (e.g., "c++", "rust")
  "compiler": "string",              // Compiler identifier (e.g., "g112", "clang1500")
  "code": "string",                  // Original source code
  "compilationOptions": [            // Array of compiler flags/options
    "-O2",
    "-g",
    "-Wall"
  ],
  "instructionSet": "string",        // Target architecture (e.g., "amd64", "arm64")
  "asm": [                          // Array of assembly objects from compile response
    {
      "text": "square(int):",       // Assembly text
      "source": null,               // Optional source mapping
      "labels": []                  // Array of label references
    },
    {
      "text": "        push    rbp",
      "source": {
        "file": null,               // Source file (usually null)
        "line": 1,                  // Source line number
        "column": 21                // Source column number
      },
      "labels": []
    }
  ],
  "labelDefinitions": {             // Optional map of label names to line numbers
    "square(int)": 1
  },
  "stderr": [                      // Optional array of compiler error/warning messages
    "warning: unused variable 'x'"
  ],
  "optimizationOutput": [          // Optional optimization remarks (if available)
    "loop vectorized"
  ]
}
```

### Output Format

The service will return a JSON response with:

```json
{
  "explanation": "string",    // The generated explanation
  "status": "success" | "error",
  "message": "string"         // Only present on error
}
```

## Implementation Details

### Lambda Function

1. **Input Validation and Sanitization**:
   - Validate required fields (`language`, `compiler`, `code`, `asm`)
   - Ensure the `asm` array is correctly formatted
   - Validate input size against defined limits
   - Check for malformed JSON structures

2. **Claude Haiku Integration**:
   - Use Anthropic Python client to interact with Claude Haiku
   - Provide structured JSON data directly to Claude
   - Use system prompt to establish the compiler analyst role
   - Set appropriate temperature and max_tokens for response generation

3. **Processing Pipeline**:
   - Extract relevant data from Compiler Explorer's compile response
   - Prepare structured JSON for Claude:
     - Preserve the original assembly structure with source mappings
     - Keep the raw asm array with all its details intact
     - Use labelDefinitions to identify function boundaries
   - Handle large assembly outputs:
     - Set a maximum line limit (e.g., 300 lines) for the assembly
     - For outputs exceeding the limit, implement intelligent selection:
       - Always include function entry points and prologue/epilogue code
       - Preserve assembly with source line mappings
       - Maintain context by including surrounding instructions
       - Add special marker objects to indicate omitted sections
       - Include metadata about truncation (original length, truncation status)
     - This approach allows Claude to understand both the content and structure
   - Process input intelligently:
     - Keep assembly grouped by function for better analysis
     - Preserve original source-to-assembly mappings
     - Identify important patterns like function boundaries and loops
     - Use structured format to highlight relationships between code and assembly

4. **Error Handling**:
   - Handle malformed requests
   - Handle Claude API errors
   - Handle rate limits
   - Provide meaningful error messages

5. **Security Measures**:
   - API key storage in AWS Parameter Store/Secrets Manager
   - Input validation and sanitization
   - Rate limiting
   - Request logging

### Claude Prompt Strategy

Instead of flattening the structured assembly data into plain text, we'll leverage Claude's ability to process JSON directly. This allows us to provide the full richness of the source-to-assembly mapping in a structured format that Claude can analyze more effectively.

The prompt will consist of:

1. **System Prompt**: Setting the expert compiler analyst role
2. **User Message**: A JSON object containing all relevant data

Here's an example structure:

```json
{
  "task": "Explain the relationship between source code and assembly output",
  "language": "c++",
  "compiler": "g++",
  "compilationOptions": ["-O2", "-g", "-Wall"],
  "instructionSet": "amd64",
  "sourceCode": "int square(int x) {\n  return x * x;\n}",
  "assembly": [
    {
      "text": "square(int):",
      "source": null,
      "labels": []
    },
    {
      "text": "        push    rbp",
      "source": {
        "line": 1,
        "column": 21
      },
      "labels": []
    },
    // Additional assembly items...
  ],
  "labelDefinitions": {
    "square(int)": 1
  },
  "compilerMessages": [],
  "optimizationRemarks": []
}
```

For the Claude Messages API, this would look like:

```python
message = client.messages.create(
    model=MODEL,
    max_tokens=MAX_TOKENS,
    system="You are an expert compiler analyst who explains the relationship between source code and assembly output. Provide clear, concise explanations that help programmers understand how their code translates to assembly.",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Explain the relationship between this source code and its assembly output."
                },
                {
                    "type": "json",
                    "json": structured_data  # The JSON object shown above
                }
            ]
        }
    ]
)
```

This approach has several advantages:
- Preserves the complete structure of the data
- Allows Claude to directly access the source-to-assembly mapping
- Eliminates the need for text-based parsing
- Makes it easier to handle large assembly outputs without losing context
- Enables more precise analysis of the relationship between source and assembly

### Terraform Configuration

1. **Lambda Resource**:
   - Python 3.12 runtime
   - Memory allocation based on expected workload
   - Timeout appropriate for Claude API interaction
   - Environment variables for configuration (API keys retrieved from Parameter Store)

2. **API Gateway Configuration**:
   - HTTP API with CORS support
   - POST route for `/explain` endpoint
   - Integration with Lambda function
   - Custom domain mapping to `api.compiler-explorer.com/explain`

3. **IAM Permissions**:
   - Lambda execution role
   - Access to Parameter Store/Secrets Manager for API keys
   - CloudWatch logging permissions

4. **Rate Limiting and Quotas**:
   - API Gateway usage plans
   - Throttling rules to prevent abuse
   - Consider token bucket algorithm for more sophisticated rate limiting

## Security Considerations

1. **API Key Management**:
   - Store Claude API key in AWS Secrets Manager or Parameter Store
   - Rotate keys periodically

2. **Input Sanitization**:
   - Validate and sanitize all inputs
   - Prevent prompt injection attacks
   - Limit input size

3. **Rate Limiting**:
   - Implement request throttling at API Gateway level
   - Consider IP-based rate limiting
   - Consider user authentication for higher rate limits

4. **Privacy**:
   - Be clear about data handling in privacy policy
   - Consider anonymizing or truncating large inputs
   - Implement appropriate logging controls

5. **Monitoring**:
   - Set up alarms for unusual usage patterns
   - Monitor costs and usage

## Cost Considerations

1. **Claude API Costs**:
   - Monitor token usage
   - Consider implementing a token budget per request
   - Set up cost alerting

2. **AWS Infrastructure Costs**:
   - Lambda execution costs
   - API Gateway request costs
   - CloudWatch logging costs

3. **Optimization Strategies**:
   - Cache common explanations
   - Implement token usage quotas
   - Consider pre-warming for high-traffic periods

## Testing Strategy

1. **Unit Tests**:
   - Test input validation
   - Test sanitization functions
   - Test prompt formatting
   - Mock Claude API responses

2. **Integration Tests**:
   - Test full request/response flow
   - Test error handling
   - Test rate limiting

3. **Load Testing**:
   - Verify performance under load
   - Test concurrency limits
   - Ensure rate limiting works correctly

## Deployment and Operations

1. **CI/CD Pipeline**:
   - Automated tests
   - Separate staging/production environments
   - Blue/green deployment strategy

2. **Monitoring**:
   - CloudWatch metrics and dashboards
   - Error rate alerting
   - Cost monitoring

3. **Logging**:
   - Request/response logging
   - Error logging
   - Usage statistics

## Future Enhancements

1. **Model Improvements**:
   - Tune prompts based on user feedback
   - Consider specialized models for different languages
   - Explore finer-grained explanations

2. **Feature Enhancements**:
   - Support for more detailed assembly analysis
   - Interactive explanations
   - Explanation of specific sections of code/assembly
   - Highlighting optimizations based on compilation flags
   - Comparing multiple compiler outputs for the same code
   - Adding community feedback to improve explanations over time

3. **Integration Options**:
   - Direct integration with Compiler Explorer UI
   - API keys for third-party integrations
   - Batch processing capabilities

## Sample Implementation

### Lambda Handler (Python)

```python
import json
import os
import re
import boto3
from anthropic import Anthropic
from botocore.exceptions import ClientError

# Initialize clients
ssm = boto3.client('ssm')
anthropic_client = None  # Initialized lazily

# Constants
MAX_CODE_LENGTH = 10000
MAX_ASM_LENGTH = 20000
MODEL = "claude-3-haiku-20240307"
MAX_TOKENS = 1024
PARAM_NAME = "/ce/claude/api-key"

def get_anthropic_client():
    """Get or initialize Anthropic client with API key from Parameter Store."""
    global anthropic_client
    if anthropic_client is None:
        try:
            response = ssm.get_parameter(Name=PARAM_NAME, WithDecryption=True)
            api_key = response['Parameter']['Value']
            anthropic_client = Anthropic(api_key=api_key)
        except ClientError as e:
            print(f"Error retrieving API key: {e}")
            raise
    return anthropic_client

def validate_input(body):
    """Validate the input request body."""
    required_fields = ['language', 'compiler', 'code', 'asm']
    for field in required_fields:
        if field not in body:
            return False, f"Missing required field: {field}"

    # Validate code length
    if len(body['code']) > MAX_CODE_LENGTH:
        return False, f"Source code exceeds maximum length of {MAX_CODE_LENGTH} characters"

    # Validate assembly format
    if not isinstance(body['asm'], list):
        return False, "Assembly must be an array"

    return True, ""

# We use prepare_structured_data to process the input for Claude

def prepare_structured_data(body):
    """Prepare a structured JSON object for Claude's consumption."""
    # Set reasonable limits
    MAX_ASSEMBLY_LINES = 300

    # Extract and validate basic fields
    structured_data = {
        "task": "Explain the relationship between source code and assembly output",
        "language": body.get('language', 'unknown'),
        "compiler": body.get('compiler', 'unknown'),
        "sourceCode": body.get('code', ''),
        "instructionSet": body.get('instructionSet', 'unknown'),
    }

    # Format compilation options
    comp_options = body.get('compilationOptions', [])
    if isinstance(comp_options, list):
        structured_data["compilationOptions"] = comp_options
    else:
        structured_data["compilationOptions"] = [str(comp_options)]

    # Process assembly array
    asm_array = body.get('asm', [])
    if len(asm_array) > MAX_ASSEMBLY_LINES:
        # If assembly is too large, we need smart truncation
        structured_data["assembly"] = select_important_assembly(asm_array, body.get('labelDefinitions', {}))
        structured_data["truncated"] = True
        structured_data["originalLength"] = len(asm_array)
    else:
        # Use the full assembly if it's within limits
        structured_data["assembly"] = asm_array
        structured_data["truncated"] = False

    # Include label definitions
    structured_data["labelDefinitions"] = body.get('labelDefinitions', {})

    # Add compiler messages if available
    stderr = body.get('stderr', [])
    if stderr and isinstance(stderr, list):
        structured_data["compilerMessages"] = stderr
    else:
        structured_data["compilerMessages"] = []

    # Add optimization remarks if available
    opt_output = body.get('optimizationOutput', [])
    if opt_output and isinstance(opt_output, list):
        structured_data["optimizationRemarks"] = opt_output
    else:
        structured_data["optimizationRemarks"] = []

    return structured_data

def select_important_assembly(asm_array, label_definitions, max_lines=300):
    """Select the most important assembly lines if the output is too large.

    This function identifies and preserves:
    1. Function boundaries (entry points and returns)
    2. Instructions with source mappings
    3. Important contextual instructions
    """
    if len(asm_array) <= max_lines:
        return asm_array

    # Identify important blocks (function boundaries, etc.)
    important_indices = set()

    # Mark label definitions as important
    for label, line_idx in label_definitions.items():
        if 0 <= line_idx < len(asm_array):
            # Add the label line and a few lines after it (function prologue)
            for i in range(line_idx, min(line_idx + 5, len(asm_array))):
                important_indices.add(i)

    # Mark function epilogues and lines with source mappings
    for idx, asm_item in enumerate(asm_array):
        if not isinstance(asm_item, dict) or 'text' not in asm_item:
            continue

        # Source mapping makes this important
        if asm_item.get('source') and asm_item['source'].get('line') is not None:
            important_indices.add(idx)

        # Function returns and epilogues are important
        text = asm_item.get('text', '').strip()
        if text in ('ret', 'leave', 'pop rbp') or text.startswith('ret '):
            # Add the return line and a few lines before it
            for i in range(max(0, idx - 3), idx + 1):
                important_indices.add(i)

    # Also include context around important lines
    context_indices = set()
    for idx in important_indices:
        # Add a few lines before and after for context
        for i in range(max(0, idx - 2), min(len(asm_array), idx + 3)):
            context_indices.add(i)

    # Combine all important indices
    all_indices = important_indices.union(context_indices)

    # If we still have too many lines, prioritize
    if len(all_indices) > max_lines:
        # Prioritize function boundaries and source mappings over context
        all_indices = list(important_indices)
        all_indices.sort()
        all_indices = all_indices[:max_lines]

    # Collect selected assembly items
    selected_assembly = []

    # Sort indices to maintain original order
    sorted_indices = sorted(all_indices)

    # Find gaps and add "omitted" markers
    last_idx = -2
    for idx in sorted_indices:
        if idx > last_idx + 1:
            # There's a gap, add a special marker
            selected_assembly.append({
                "text": f"... ({idx - last_idx - 1} lines omitted) ...",
                "isOmissionMarker": True
            })

        # Add the actual assembly item
        if 0 <= idx < len(asm_array):
            selected_assembly.append(asm_array[idx])

        last_idx = idx

    # Add a final omission marker if needed
    if last_idx < len(asm_array) - 1:
        selected_assembly.append({
            "text": f"... ({len(asm_array) - last_idx - 1} lines omitted) ...",
            "isOmissionMarker": True
        })

    return selected_assembly

# We use structured JSON content instead of text-based prompts

def create_response(status_code, body):
    """Create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        },
        'body': json.dumps(body)
    }

def lambda_handler(event, context):
    """Lambda handler function."""
    # Handle OPTIONS request (CORS preflight)
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))

        # Validate input
        valid, error_message = validate_input(body)
        if not valid:
            return create_response(400, {'status': 'error', 'message': error_message})

        # Prepare structured data for Claude
        structured_data = prepare_structured_data(body)

        # Call Claude API with JSON structure
        client = get_anthropic_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system="You are an expert compiler analyst who explains the relationship between source code and assembly output. Provide clear, concise explanations that help programmers understand how their code translates to assembly.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Explain the relationship between this source code and its assembly output."
                        },
                        {
                            "type": "json",
                            "json": structured_data
                        }
                    ]
                }
            ]
        )

        explanation = message.content[0].text

        # Return success response
        return create_response(200, {
            'status': 'success',
            'explanation': explanation
        })

    except json.JSONDecodeError:
        return create_response(400, {'status': 'error', 'message': 'Invalid JSON in request body'})
    except Exception as e:
        print(f"Error: {str(e)}")
        return create_response(500, {'status': 'error', 'message': 'Internal server error'})
```

### Terraform Configuration (Sample)

```hcl
# IAM Role for Lambda
resource "aws_iam_role" "explain_lambda_role" {
  name = "explain_lambda_execution_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# SSM Parameter Store access policy
resource "aws_iam_policy" "explain_ssm_policy" {
  name = "explain_ssm_access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "ssm:GetParameter",
      ]
      Effect = "Allow"
      Resource = "arn:aws:ssm:${var.region}:${var.account_id}:parameter/ce/claude/api-key"
    }]
  })
}

# Logging policy
resource "aws_iam_policy" "explain_logging_policy" {
  name = "explain_lambda_logging"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Effect = "Allow"
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# Attach policies to role
resource "aws_iam_role_policy_attachment" "explain_ssm_attach" {
  role = aws_iam_role.explain_lambda_role.name
  policy_arn = aws_iam_policy.explain_ssm_policy.arn
}

resource "aws_iam_role_policy_attachment" "explain_logging_attach" {
  role = aws_iam_role.explain_lambda_role.name
  policy_arn = aws_iam_policy.explain_logging_policy.arn
}

# Lambda function
resource "aws_lambda_function" "explain" {
  function_name = "explain"
  description = "Explain compiler assembly output using Claude"
  s3_bucket = aws_s3_bucket.compiler-explorer.bucket
  s3_key = "lambdas/lambda-package.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambda/lambda-package.zip")
  role = aws_iam_role.explain_lambda_role.arn
  handler = "explain.lambda_handler"
  runtime = "python3.12"
  timeout = 30
  memory_size = 256

  environment {
    variables = {
      # Additional environment variables if needed
    }
  }
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "explain" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id
  integration_uri = aws_lambda_function.explain.invoke_arn
  integration_type = "AWS_PROXY"
  integration_method = "POST"
}

# API Gateway Route
resource "aws_apigatewayv2_route" "explain" {
  api_id = aws_apigatewayv2_api.ce_pub_api.id
  route_key = "POST /explain"
  target = "integrations/${aws_apigatewayv2_integration.explain.id}"
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "explain_api" {
  statement_id = "AllowAPIGatewayInvoke"
  action = "lambda:InvokeFunction"
  function_name = aws_lambda_function.explain.function_name
  principal = "apigateway.amazonaws.com"
  source_arn = "${aws_apigatewayv2_api.ce_pub_api.execution_arn}/*/*"
}
```

## Implementation Checklist

### Infrastructure Setup

- [ ] Create Terraform configuration for Lambda function
- [ ] Create Terraform configuration for API Gateway
- [ ] Set up API key storage in Parameter Store/Secrets Manager
- [ ] Configure CloudWatch logging
- [ ] Implement rate limiting

### Lambda Implementation

- [ ] Set up Python project structure
- [ ] Implement input validation and sanitization
- [ ] Create Claude prompt template
- [ ] Implement Claude API integration
- [ ] Add error handling and logging
- [ ] Write unit tests

### API Configuration

- [ ] Configure API Gateway routes
- [ ] Set up CORS
- [ ] Configure request/response mapping
- [ ] Implement rate limiting
- [ ] Set up custom domain

### Testing

- [ ] Write unit tests for validation and sanitization
- [ ] Create integration tests
- [ ] Perform security testing
- [ ] Test rate limiting and quotas
- [ ] Load testing

### Documentation

- [ ] Update API documentation
- [ ] Add usage examples
- [ ] Document rate limits and quotas
- [ ] Create operational runbook

### Deployment

- [ ] Deploy to staging environment
- [ ] Validate functionality and performance
- [ ] Deploy to production
- [ ] Set up monitoring and alerting

## Conclusion

The Claude Explain service will provide valuable insights into compiler behavior for Compiler Explorer users. By leveraging Claude Haiku's AI capabilities, we can offer explanations that help users understand the relationship between their source code and the resulting assembly.

This service is designed to be maintainable, secure, and cost-effective, with room for future enhancements based on user feedback and evolving requirements.
