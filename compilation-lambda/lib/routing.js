const { dynamodb, sqs, GetItemCommand, SendMessageCommand } = require('./aws-clients');

// Environment variables - read dynamically to support environment switching in tests
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';

function getEnvironmentName() {
    return process.env.ENVIRONMENT_NAME || 'unknown';
}

function getSqsQueueUrl() {
    return process.env.SQS_QUEUE_URL || '';
}

/**
 * Build a queue URL from the template SQS_QUEUE_URL and a specific queue name
 * @param {string} queueName - Name of the queue to route to
 * @returns {string} Full SQS queue URL
 */
function buildQueueUrl(queueName) {
    const templateUrl = getSqsQueueUrl();
    if (!templateUrl) {
        throw new Error('SQS_QUEUE_URL environment variable not set');
    }

    // Extract the base URL (everything before the last slash)
    const lastSlashIndex = templateUrl.lastIndexOf('/');
    if (lastSlashIndex === -1) {
        throw new Error('Invalid SQS_QUEUE_URL format');
    }

    // Ensure queue name has .fifo suffix (all queues in this system are FIFO)
    const fifoQueueName = queueName.endsWith('.fifo') ? queueName : queueName + '.fifo';

    const baseUrl = templateUrl.substring(0, lastSlashIndex + 1);
    return baseUrl + fifoQueueName;
}

// DynamoDB table for compiler routing
const COMPILER_ROUTING_TABLE = 'CompilerRouting';

// In-memory cache for routing lookups (persists until Lambda restart)
const routingCache = new Map();

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

        // Check cache first
        const cacheKey = compositeKey;
        const cachedEntry = routingCache.get(cacheKey);
        if (cachedEntry) {
            console.info(`Routing cache hit for compiler: ${compilerId}`);
            return cachedEntry;
        }

        // Look up compiler in DynamoDB routing table using composite key
        console.info(`DynamoDB routing lookup start for compiler: ${compilerId}`);
        const response = await dynamodb.send(new GetItemCommand({
            TableName: COMPILER_ROUTING_TABLE,
            Key: {
                compilerId: { S: compositeKey }
            }
        }));

        let item = response.Item;

        if (!item) {
            // Fallback: try old format (without environment prefix) for backward compatibility
            console.info(`Composite key not found for ${compositeKey}, trying legacy format`);
            const fallbackResponse = await dynamodb.send(new GetItemCommand({
                TableName: COMPILER_ROUTING_TABLE,
                Key: {
                    compilerId: { S: compilerId }
                }
            }));

            item = fallbackResponse.Item;
            if (item) {
                console.warn(`Using legacy routing entry for ${compilerId} - consider migration`);
                console.info(`DynamoDB routing lookup end for compiler: ${compilerId}, using fallback: found`);
            } else {
                console.info(`DynamoDB routing lookup end for compiler: ${compilerId}, using fallback: not found`);
            }
        } else {
            console.info(`DynamoDB routing lookup end for compiler: ${compilerId}, using composite key`);
        }

        if (item) {
            const routingType = item.routingType?.S || 'queue';

            if (routingType === 'url') {
                const targetUrl = item.targetUrl?.S || '';
                if (targetUrl) {
                    const result = {
                        type: 'url',
                        target: targetUrl,
                        environment: item.environment?.S || ''
                    };
                    // Cache the result
                    routingCache.set(cacheKey, result);
                    console.info(`Compiler ${compilerId} routed to URL: ${targetUrl}`);
                    console.info(`Routing lookup complete for compiler: ${compilerId}`);
                    return result;
                }
            } else {
                // Queue routing - use queueName from DynamoDB to build full queue URL
                const queueName = item.queueName?.S;
                if (queueName) {
                    const queueUrl = buildQueueUrl(queueName);
                    const result = {
                        type: 'queue',
                        target: queueUrl,
                        environment: item.environment?.S || ''
                    };
                    // Cache the result
                    routingCache.set(cacheKey, result);
                    console.info(`Compiler ${compilerId} routed to queue: ${queueName} (${queueUrl})`);
                    console.info(`Routing lookup complete for compiler: ${compilerId}`);
                    return result;
                } else {
                    // Fallback to default queue if no queueName specified
                    const result = {
                        type: 'queue',
                        target: getSqsQueueUrl(),
                        environment: item.environment?.S || ''
                    };
                    // Cache the result
                    routingCache.set(cacheKey, result);
                    console.info(`Compiler ${compilerId} routed to default queue (no queueName in DynamoDB)`);
                    console.info(`Routing lookup complete for compiler: ${compilerId}`);
                    return result;
                }
            }
        }

        // No routing found, use default queue
        console.info(`No routing found for compiler ${compilerId}, using default queue`);
        const result = {
            type: 'queue',
            target: getSqsQueueUrl(),
            environment: 'unknown'
        };
        // Cache the default result
        routingCache.set(cacheKey, result);
        console.info(`Routing lookup complete for compiler: ${compilerId}, using default queue`);
        return result;

    } catch (error) {
        // On any error, fall back to default queue
        console.warn(`Failed to lookup routing for compiler ${compilerId}:`, error);
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

    try {
        const messageJson = JSON.stringify(messageBody);

        console.info(`SQS send start for GUID: ${guid} to queue`);
        await sqs.send(new SendMessageCommand({
            QueueUrl: queueUrl,
            MessageBody: messageJson,
            MessageGroupId: 'default',
            MessageDeduplicationId: guid
        }));
        console.info(`SQS send end for GUID: ${guid}`);

    } catch (error) {
        console.error(`Failed to send message to SQS (${queueUrl}):`, error);
        throw new Error(`Failed to send message to SQS (${queueUrl}): ${error.message}`);
    }
}

module.exports = {
    lookupCompilerRouting,
    sendToSqs,
    parseRequestBody,
    buildQueueUrl
};
