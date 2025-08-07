const { DynamoDBClient, GetItemCommand } = require('@aws-sdk/client-dynamodb');
const { SQSClient, SendMessageCommand } = require('@aws-sdk/client-sqs');

const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const AWS_ACCOUNT_ID = '052730242331';

// Initialize AWS clients
const dynamodb = new DynamoDBClient({ region: AWS_REGION });
const sqs = new SQSClient({ region: AWS_REGION });

module.exports = {
    dynamodb,
    sqs,
    AWS_ACCOUNT_ID,
    GetItemCommand,
    SendMessageCommand
};