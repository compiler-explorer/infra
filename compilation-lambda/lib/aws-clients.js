const { DynamoDBClient, GetItemCommand } = require('@aws-sdk/client-dynamodb');
const { SQSClient, SendMessageCommand } = require('@aws-sdk/client-sqs');
const { S3Client } = require('@aws-sdk/client-s3');
const { SSMClient, GetParameterCommand } = require('@aws-sdk/client-ssm');
const { NodeHttpHandler } = require('@smithy/node-http-handler');
const https = require('https');

const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const AWS_ACCOUNT_ID = '052730242331';

// Create optimized HTTPS agent for connection reuse
const httpsAgent = new https.Agent({
    keepAlive: true,
    keepAliveMsecs: 1000,
    maxSockets: 50,
    maxFreeSockets: 10,
    timeout: 60000,
    freeSocketTimeout: 30000
});

// Optimized AWS client configuration for production Lambda performance
const clientConfig = {
    region: AWS_REGION,
    requestHandler: new NodeHttpHandler({
        httpsAgent,
        connectionTimeout: 1000,  // Faster connection setup
        socketTimeout: 3000       // Reduced timeout for faster failures
    }),
    maxAttempts: 3,  // Increased retries for better reliability
    retryMode: 'adaptive'  // Intelligent retry strategy
};

// Initialize AWS clients with optimized configuration
const dynamodb = new DynamoDBClient(clientConfig);
const sqs = new SQSClient(clientConfig);
const ssm = new SSMClient(clientConfig);

// S3 client - using a function to create on-demand since it's only needed for large results
let s3Client = null;
const getS3Client = () => {
    if (!s3Client) {
        s3Client = new S3Client(clientConfig);
    }
    return s3Client;
};

module.exports = {
    dynamodb,
    sqs,
    ssm,
    getS3Client,
    AWS_ACCOUNT_ID,
    GetItemCommand,
    SendMessageCommand,
    GetParameterCommand
};
