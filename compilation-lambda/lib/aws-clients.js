const { DynamoDBClient, GetItemCommand } = require('@aws-sdk/client-dynamodb');
const { SQSClient, SendMessageCommand } = require('@aws-sdk/client-sqs');
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

// Optimized AWS client configuration for Lambda performance
const clientConfig = {
    region: AWS_REGION,
    requestHandler: new NodeHttpHandler({
        httpsAgent,
        connectionTimeout: 2000,
        socketTimeout: 5000
    }),
    maxAttempts: 2
};

// Initialize AWS clients with optimized configuration
const dynamodb = new DynamoDBClient(clientConfig);
const sqs = new SQSClient(clientConfig);

module.exports = {
    dynamodb,
    sqs,
    AWS_ACCOUNT_ID,
    GetItemCommand,
    SendMessageCommand
};
