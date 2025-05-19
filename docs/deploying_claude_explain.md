# Deploying the Claude Explain Service

This document outlines the steps to deploy the Claude Explain service, which provides AI-powered explanations of compiler output for Compiler Explorer users.

## Prerequisites

1. An [Anthropic API key](https://console.anthropic.com/settings/keys) for accessing the Claude API
2. AWS CLI configured with appropriate permissions
3. Terraform installed (for deploying AWS resources)

## Deployment Steps

### 1. Store the Claude API key in AWS Parameter Store

The service expects the Claude API key to be stored in AWS Parameter Store. Use the provided script to set it up:

```bash
# Run from the repository root
./setup-claude-api-key.sh your-anthropic-api-key
```

### 2. Deploy the Lambda function and API Gateway

The Lambda function and API Gateway configuration are defined in Terraform. Deploy them using:

```bash
cd terraform
terraform init
terraform plan  # Review the changes
terraform apply # Apply the changes
```

This will create:
- The Lambda function for handling explain requests
- API Gateway integration for the `/explain` endpoint
- Required IAM permissions

### 3. Verify the deployment

After deployment, you can test the API endpoint using curl:

```bash
# Replace with your actual API Gateway URL
API_URL="https://api.compiler-explorer.com/explain"

# Test with a simple C++ function
curl -X POST $API_URL \
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
          "file": null,
          "line": 1,
          "column": 21
        },
        "labels": []
      },
      {
        "text": "        imul    eax, edi",
        "source": {
          "file": null,
          "line": 2,
          "column": 10
        },
        "labels": []
      },
      {
        "text": "        ret",
        "source": {
          "file": null,
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

## Monitoring and Maintenance

### CloudWatch Logs

The Lambda function logs to CloudWatch. You can monitor these logs for errors and performance:

```bash
aws logs get-log-events --log-group-name /aws/lambda/explain --log-stream-name <log-stream-name>
```

### API Key Rotation

If you need to rotate the Claude API key, simply run the setup script again with the new key:

```bash
./setup-claude-api-key.sh your-new-anthropic-api-key
```

### Cost Monitoring

Monitor the costs associated with:
1. Claude API usage through Anthropic's console
2. Lambda invocations and API Gateway requests through AWS Cost Explorer

## Troubleshooting

### Common Issues

1. **403 Forbidden errors**: Check the IAM permissions for the Lambda function
2. **500 Internal Server errors**: Check CloudWatch logs for details
3. **Claude API errors**: Verify the API key is correct and has sufficient permissions

### Debugging Tips

- Enable detailed CloudWatch logging by setting the log level to DEBUG
- Test the Lambda function directly using the AWS Console
- Verify the SSM Parameter is correctly set up:
  ```bash
  aws ssm get-parameter --name /ce/claude/api-key --with-decryption
  ```

## Security Considerations

- The Claude API key is stored securely in SSM Parameter Store as a SecureString
- The Lambda function has minimal IAM permissions
- API Gateway includes rate limiting to prevent abuse
- CORS is configured for the Compiler Explorer domain only
