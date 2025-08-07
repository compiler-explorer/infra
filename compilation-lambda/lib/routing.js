const { dynamodb, sqs, GetItemCommand, SendMessageCommand } = require('./aws-clients');

// Environment variables - read dynamically to support environment switching in tests
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';

function getEnvironmentName() {
    return process.env.ENVIRONMENT_NAME || 'unknown';
}

function getSqsQueueUrl() {
    return process.env.SQS_QUEUE_URL || '';
}

// DynamoDB table for compiler routing
const COMPILER_ROUTING_TABLE = 'CompilerRouting';

/**
 * Parse request body based on content type
 * Supports both JSON and plain text (for source code)
 */
function parseRequestBody(body, contentType) {
    if (!body) return {};

    // Check if content type indicates JSON
    if (contentType && contentType.toLowerCase().includes('application/json')) {
        try {
            return JSON.parse(body);
        } catch (error) {
            console.warn('Failed to parse JSON body, treating as plain text');
            return { source: body };
        }
    } else {
        // Plain text body - treat as source code
        return { source: body };
    }
}

/**
 * Look up routing information for a specific compiler using DynamoDB
 * Returns routing decision with type and target information
 * Uses environment-prefixed composite key for isolation
 */
async function lookupCompilerRouting(compilerId) {
    const lookupStart = Date.now();
    try {
        // Create composite key with environment prefix for isolation
        const environmentName = getEnvironmentName();
        const compositeKey = `${environmentName}#${compilerId}`;

        // Look up compiler in DynamoDB routing table using composite key
        const primaryLookupStart = Date.now();
        const response = await dynamodb.send(new GetItemCommand({
            TableName: COMPILER_ROUTING_TABLE,
            Key: {
                compilerId: { S: compositeKey }
            }
        }));
        const primaryLookupDuration = Date.now() - primaryLookupStart;

        let item = response.Item;
        let totalDynamodbTime = primaryLookupDuration;

        if (!item) {
            // Fallback: try old format (without environment prefix) for backward compatibility
            console.info(`Composite key not found for ${compositeKey}, trying legacy format`);
            const fallbackLookupStart = Date.now();
            const fallbackResponse = await dynamodb.send(new GetItemCommand({
                TableName: COMPILER_ROUTING_TABLE,
                Key: {
                    compilerId: { S: compilerId }
                }
            }));
            const fallbackLookupDuration = Date.now() - fallbackLookupStart;
            totalDynamodbTime += fallbackLookupDuration;

            item = fallbackResponse.Item;
            if (item) {
                console.warn(`Using legacy routing entry for ${compilerId} - consider migration`);
                console.info(`DynamoDB timing: primary lookup ${primaryLookupDuration}ms, fallback lookup ${fallbackLookupDuration}ms (total: ${totalDynamodbTime}ms)`);
            } else {
                console.info(`DynamoDB timing: primary lookup ${primaryLookupDuration}ms, fallback lookup ${fallbackLookupDuration}ms (total: ${totalDynamodbTime}ms) - no routing found`);
            }
        } else {
            console.info(`DynamoDB timing: primary lookup ${primaryLookupDuration}ms - composite key found`);
        }

        if (item) {
            const routingType = item.routingType?.S || 'queue';
            const totalLookupDuration = Date.now() - lookupStart;

            if (routingType === 'url') {
                const targetUrl = item.targetUrl?.S || '';
                if (targetUrl) {
                    console.info(`Compiler ${compilerId} routed to URL: ${targetUrl}`);
                    console.info(`Total routing lookup time: ${totalLookupDuration}ms`);
                    return {
                        type: 'url',
                        target: targetUrl,
                        environment: item.environment?.S || ''
                    };
                }
            } else {
                // Queue routing - use environment's SQS_QUEUE_URL directly
                const queueName = item.queueName?.S || 'default queue';
                console.info(`Compiler ${compilerId} routed to queue: ${queueName}`);
                console.info(`Total routing lookup time: ${totalLookupDuration}ms`);
                return {
                    type: 'queue',
                    target: getSqsQueueUrl(),
                    environment: item.environment?.S || ''
                };
            }
        }

        // No routing found, use default queue
        console.info(`No routing found for compiler ${compilerId}, using default queue`);
        const totalLookupDuration = Date.now() - lookupStart;
        console.info(`Total routing lookup time: ${totalLookupDuration}ms`);
        return {
            type: 'queue',
            target: getSqsQueueUrl(),
            environment: 'unknown'
        };

    } catch (error) {
        // On any error, fall back to default queue
        const totalLookupDuration = Date.now() - lookupStart;
        console.warn(`Failed to lookup routing for compiler ${compilerId} after ${totalLookupDuration}ms:`, error);
        return {
            type: 'queue',
            target: getSqsQueueUrl(),
            environment: 'unknown'
        };
    }
}

/**
 * Send compilation request to SQS queue as RemoteCompilationRequest
 */
async function sendToSqs(guid, compilerId, body, isCmake, headers, queueUrl) {
    if (!queueUrl) {
        throw new Error('No queue URL available (neither DynamoDB lookup nor SQS_QUEUE_URL env var set)');
    }

    // Parse body based on content type
    const contentType = headers['content-type'] || headers['Content-Type'] || '';
    const requestData = parseRequestBody(body, contentType);

    if (typeof requestData !== 'object') {
        console.warn(`Request data is not an object: ${JSON.stringify(requestData).substring(0, 100)}...`);
    }

    // Start with Lambda-specific fields
    const messageBody = {
        guid,
        compilerId,
        isCMake: isCmake,
        headers, // Preserve original headers for response formatting
        ...requestData // Merge all fields from the original request first (preserves original values)
    };

    // Add defaults for fields that are required by the consumer but might be missing
    messageBody.source = messageBody.source || '';
    messageBody.options = messageBody.options || [];
    messageBody.filters = messageBody.filters || {};
    messageBody.backendOptions = messageBody.backendOptions || {};
    messageBody.tools = messageBody.tools || [];
    messageBody.libraries = messageBody.libraries || [];
    messageBody.files = messageBody.files || [];
    messageBody.executeParameters = messageBody.executeParameters || {};

    const sqsStart = Date.now();
    try {
        const messageJson = JSON.stringify(messageBody);

        await sqs.send(new SendMessageCommand({
            QueueUrl: queueUrl,
            MessageBody: messageJson,
            MessageGroupId: 'default',
            MessageDeduplicationId: guid
        }));

        const sqsDuration = Date.now() - sqsStart;
        console.info(`SQS timing: message sent in ${sqsDuration}ms`);

    } catch (error) {
        const sqsDuration = Date.now() - sqsStart;
        console.error(`Failed to send message to SQS after ${sqsDuration}ms:`, error);
        throw new Error(`Failed to send message to SQS: ${error.message}`);
    }
}

module.exports = {
    lookupCompilerRouting,
    sendToSqs,
    parseRequestBody
};
