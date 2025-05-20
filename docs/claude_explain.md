# Claude Explain Service Design Document

## Overview

The Claude Explain service will provide AI-powered explanations of compiler output for Compiler Explorer users. This service will receive compiled code and its resulting assembly, then use Claude 3.5 Haiku to generate explanations that help users understand the relationship between their source code and the generated assembly.

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
  "message": "string",        // Only present on error
  "model": "string",          // The Claude model used (e.g., "claude-3-haiku-20240307")
  "usage": {
    "input_tokens": 123,      // Number of input tokens used in the request
    "output_tokens": 456,     // Number of output tokens generated
    "total_tokens": 579       // Total tokens used (input + output)
  },
  "cost": {
    "input_cost": 0.000123,   // Cost in USD for input tokens
    "output_cost": 0.000456,  // Cost in USD for output tokens
    "total_cost": 0.000579    // Total cost in USD
  }
}
```

## Implementation Details

### Lambda Function

1. **Input Validation and Sanitization**:
   - ✓ Validate required fields (`language`, `compiler`, `code`, `asm`)
   - ✓ Ensure the `asm` array is correctly formatted
   - ✓ Validate input size against defined limits
   - ✓ Check for malformed JSON structures

2. **Claude Integration**:
   - ✓ Use Anthropic Python client to interact with Claude 3 Haiku
   - ✓ Provide structured JSON data as a string to Claude
   - ✓ Use system prompt to establish the compiler analyst role
   - ✓ Set appropriate max_tokens for response generation

3. **Processing Pipeline**:
   - ✓ Extract relevant data from Compiler Explorer's compile response
   - ✓ Prepare structured JSON for Claude:
     - ✓ Preserve the original assembly structure with source mappings
     - ✓ Keep the raw asm array with all its details intact
     - ✓ Use labelDefinitions to identify function boundaries
   - ✓ Handle large assembly outputs:
     - ✓ Set a maximum line limit (300 lines) for the assembly
     - ✓ For outputs exceeding the limit, implement intelligent selection:
       - ✓ Always include function entry points and prologue/epilogue code
       - ✓ Preserve assembly with source line mappings
       - ✓ Maintain context by including surrounding instructions
       - ✓ Add special marker objects to indicate omitted sections
       - ✓ Include metadata about truncation (original length, truncation status)
     - ✓ This approach allows Claude to understand both the content and structure
   - ✓ Process input intelligently:
     - ✓ Keep assembly grouped by function for better analysis
     - ✓ Preserve original source-to-assembly mappings
     - ✓ Identify important patterns like function boundaries and loops
     - ✓ Use structured format to highlight relationships between code and assembly

4. **Error Handling**:
   - ✓ Handle malformed requests
   - ✓ Handle Claude API errors
   - ✓ Handle HTTP connection issues
   - ✓ Provide meaningful error messages

5. **Security Measures**:
   - ✓ API key storage in AWS Parameter Store/Secrets Manager
   - ✓ Input validation and sanitization
   - ✓ Local file-based API key for development
   - ✓ Request logging

### Claude Prompt Strategy

Instead of flattening the structured assembly data into plain text, we'll provide the structured JSON data as a string. While the Anthropic API doesn't support direct JSON objects with "type": "json" content blocks (as initially thought), sending the JSON as a string with "type": "text" is effective. Claude is still able to understand and process the structured format, allowing us to provide the full richness of the source-to-assembly mapping.

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
    system="""You are an expert in assembly code and programming languages, helping users of the Compiler Explorer website understand how their code compiles to assembly.
    Provide clear, concise explanations. Focus on key transformations, optimizations, and important assembly patterns.
    Explanations should be educational and highlight why certain code constructs generate specific assembly instructions.
    Give no commentary on the original source: it is expected the user already understands their input, and is only looking for guidance on the assembly output.
    If it makes it easiest to explain, note the corresponding parts of the source code, but do not focus on this.
    Do not give an overall conclusion.
    Be precise and accurate about CPU features and optimizations - avoid making incorrect claims about branch prediction or other hardware details.""",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Explain the relationship between this source code and its assembly output."
                },
                {
                    "type": "text",
                    "text": json.dumps(structured_data)  # The JSON object serialized as a string
                }
            ]
        }
    ]
)
```

This approach has several advantages:
- Preserves the complete structure of the data
- Allows Claude to access the source-to-assembly mapping in a structured way
- Sends data in a format Claude can parse and understand
- Makes it easier to handle large assembly outputs without losing context
- Enables more precise analysis of the relationship between source and assembly
- Works correctly with the Anthropic API which requires using "type": "text" rather than "type": "json"

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

## Implementation Dependencies

The implementation follows these dependency chains:

1. **Infrastructure Dependencies**:
   - Parameter Store setup → Lambda function deployment
   - IAM Roles/Policies → Lambda function deployment
   - Lambda deployment → API Gateway integration
   - API Gateway setup → CORS configuration

2. **Implementation Dependencies**:
   - Input validation → Claude integration
   - Structured data preparation → Claude prompt design
   - Lambda handler → Error handling implementation
   - API Gateway configuration → Rate limiting setup

## Security Considerations

1. **API Key Management**:
   - Store Claude API key in AWS Secrets Manager or Parameter Store
   - Rotate keys periodically

2. **Input Sanitization**:
   - Validate and sanitize all inputs
   - Limit input size for source code and assembly
   - **Note on Prompt Injection**:
     - As an open-source project, typical prompt injection concerns are minimal:
       - System details are already public in the repository
       - The technical nature of compiler explanations limits content misuse
       - Users getting misleading explanations primarily affects only themselves
     - Basic mitigation is still reasonable:
       - Validate JSON structure for proper parsing
       - Simple size limits to prevent resource abuse
       - Basic system prompt that focuses the model on compiler explanation

3. **Rate Limiting**:
   - Implement request throttling at API Gateway level
   - Consider IP-based rate limiting
   - Consider user authentication for higher rate limits

4. **Resource Protection**:
   - Implement strict timeouts for request processing
   - Add circuit breakers to detect and prevent abuse
   - Set hard limits on output token generation

5. **Privacy**:
   - **Note on Data Handling**:
     - Compiler Explorer's UI will display a consent form before sending code to Anthropic
     - The existing CE privacy policy will be updated to mention this feature specifically
     - No need for additional PII protection beyond what's already in CE
   - Implement appropriate logging controls for operational needs

6. **Monitoring**:
   - Set up alarms for unusual usage patterns
   - Monitor costs and usage
   - Create alerting for suspicious request patterns

## Cost Considerations

1. **Claude API Costs**:
   - Claude 3.5 Haiku is priced at $0.80/million input tokens and $4.00/million output tokens (as of November 2024)
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
MAX_CODE_LENGTH = 10000  # 10K chars should be enough for most source files
MAX_ASM_LENGTH = 20000   # 20K chars for assembly output
MODEL = "claude-3-haiku-20240307"
MAX_TOKENS = 1024  # Adjust based on desired explanation length
PARAM_NAME = "/ce/claude/api-key"  # Stored in Parameter Store

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
            system="""You are an expert compiler analyst who explains the relationship between source code and assembly output.
    Provide clear, concise explanations that help programmers understand how their code translates to assembly.
    Focus on key transformations, optimizations, and important assembly patterns.
    Explanations should be educational and highlight why certain code constructs generate specific assembly instructions.""",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Explain the relationship between this source code and its assembly output."
                        },
                        {
                            "type": "text",
                            "text": json.dumps(structured_data)
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
      Resource = "arn:aws:ssm:${local.region}:${data.aws_caller_identity.current.account_id}:parameter/ce/claude/api-key"
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

- [x] Create Terraform configuration for Lambda function
- [x] Create Terraform configuration for API Gateway
- [ ] Set up API key storage in Parameter Store/Secrets Manager
- [x] Configure CloudWatch logging
- [ ] Implement rate limiting

### Lambda Implementation

- [x] Set up Python project structure
- [x] Implement input validation and sanitization
- [x] Create Claude prompt template
- [x] Implement Claude API integration
- [x] Add error handling and logging
- [x] Write unit tests

### API Configuration

- [x] Configure API Gateway routes
- [x] Set up CORS
- [x] Configure request/response mapping
- [ ] Implement rate limiting
- [ ] Set up custom domain

### Testing

- [x] Write unit tests for validation and sanitization
- [x] Create integration tests
- [ ] Perform security testing
- [ ] Test rate limiting and quotas
- [ ] Load testing

### Documentation

- [x] Update API documentation
- [x] Add usage examples
- [ ] Document rate limits and quotas
- [x] Create operational runbook

### Deployment

- [ ] Deploy to staging environment
- [ ] Validate functionality and performance
- [ ] Deploy to production
- [ ] Set up monitoring and alerting

### Compiler Explorer Integration

- [ ] Implement consent UI before sending code to Anthropic
- [ ] Update CE privacy policy to mention this feature specifically
- [ ] Add "Explain" button/option in the compiler output UI
- [ ] Implement API client in CE frontend
- [ ] Handle and display explanations in the CE UI
- [ ] Add explanations to compiler tooltip options
- [ ] Support markdown formatting in explanations
- [ ] Add user feedback mechanism for explanation quality
- [ ] Create fallback behavior for rate limiting or service unavailability

## Current Implementation Status

The core Claude Explain service has been implemented with the following features:

- ✅ Lambda function with Python 3.12 runtime
- ✅ Input validation and smart assembly processing
- ✅ Integration with Anthropic API (Claude 3 Haiku model)
- ✅ Error handling and response formatting
- ✅ Comprehensive unit tests
- ✅ Local development HTTP server
- ✅ Terraform configuration for AWS deployment
- ✅ Documentation for developers and users

Key features ready for deployment:

- ✅ Local development server with secure file-based API key handling
- ✅ Smart assembly truncation for large inputs
- ✅ CORS support for browser integration
- ✅ Test script for local verification
- ✅ Error handling for various API failure modes

Remaining tasks before production release:

- Deploy to AWS staging environment
- Set up production API key and parameter store
- Implement rate limiting
- Configure domain and DNS
- Create monitoring and alerting
- Integrate with Compiler Explorer UI

## Conclusion

The Claude Explain service will provide valuable insights into compiler behavior for Compiler Explorer users. By leveraging Claude Haiku's AI capabilities, we can offer explanations that help users understand the relationship between their source code and the resulting assembly.

This service is designed to be maintainable, secure, and cost-effective, with room for future enhancements based on user feedback and evolving requirements.

## Notes from Matt on prompt stuff

- Need to stop claude confidently talking about branch prediction, e.g. "Branch Prediction: The code includes branch prediction hints (endbr64) to help the CPU predict the control flow and improve performance." - These are _not_ branch prediction hints. Now updated the prompt a bit.
- Consider using a more expensive model to avoid this? Now using Haiku 3.5
- it's not good things like counting...so yeah maybe a better model: e.g. "Scalar Fallback: If the array length is small (less than or equal to 6), the compiler falls back to a scalar implementation that processes the elements one by one." when in fact it was looking at: "  lea eax, -1[rsi] |   cmp eax, 6 | jbe ..."
- should consider prompt caching
