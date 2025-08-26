const { dynamodb, sqs, ssm, GetItemCommand, SendMessageCommand, GetParameterCommand } = require('./aws-clients');

// Environment variables - read dynamically to support environment switching in tests
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';

// Cache for active color (with TTL)
let activeColorCache = {
    color: null,
    timestamp: 0,
    TTL: 30000 // 30 seconds TTL
};

function getEnvironmentName() {
    return process.env.ENVIRONMENT_NAME || 'unknown';
}

function getBlueQueueUrl() {
    return process.env.SQS_QUEUE_URL_BLUE || '';
}

function getGreenQueueUrl() {
    return process.env.SQS_QUEUE_URL_GREEN || '';
}

/**
 * Get the active color (blue/green) from SSM Parameter Store with caching
 * @returns {Promise<string>} The active color ('blue' or 'green')
 */
async function getActiveColor() {
    const now = Date.now();

    // Check cache
    if (activeColorCache.color && (now - activeColorCache.timestamp) < activeColorCache.TTL) {
        console.info(`Active color cache hit: ${activeColorCache.color}`);
        return activeColorCache.color;
    }

    const environmentName = getEnvironmentName();
    const paramName = `/compiler-explorer/${environmentName}/active-color`;

    try {
        console.info(`Fetching active color from SSM: ${paramName}`);
        const response = await ssm.send(new GetParameterCommand({
            Name: paramName
        }));

        const color = response.Parameter?.Value || 'blue';

        // Update cache
        activeColorCache = {
            color: color,
            timestamp: now,
            TTL: activeColorCache.TTL
        };

        console.info(`Active color from SSM: ${color}`);
        return color;
    } catch (error) {
        console.warn(`Failed to get active color from SSM, defaulting to blue:`, error);
        return 'blue';
    }
}

/**
 * Get the appropriate SQS queue URL based on active color
 * @returns {Promise<string>} The SQS queue URL for the active color
 */
async function getColoredQueueUrl() {
    const activeColor = await getActiveColor();

    const queueUrl = activeColor === 'green' ? getGreenQueueUrl() : getBlueQueueUrl();

    if (!queueUrl) {
        throw new Error(`Queue URL for active color '${activeColor}' not configured in environment variables`);
    }

    console.info(`Using ${activeColor} queue: ${queueUrl}`);
    return queueUrl;
}

/**
 * Build a queue URL from a template queue URL and a specific queue name
 * For color-specific queues, this function ensures routing to the active color
 * @param {string} queueName - Name of the queue to route to
 * @param {string} activeColor - The active color ('blue' or 'green')
 * @returns {string} Full SQS queue URL for the active color
 */
function buildQueueUrl(queueName, activeColor) {
    // Get the active color's queue URL as template
    const templateUrl = activeColor === 'green' ? getGreenQueueUrl() : getBlueQueueUrl();
    if (!templateUrl) {
        throw new Error(`Queue URL for active color '${activeColor}' not configured in environment variables`);
    }

    // Extract the base URL (everything before the last slash)
    const lastSlashIndex = templateUrl.lastIndexOf('/');
    if (lastSlashIndex === -1) {
        throw new Error('Invalid queue URL format');
    }

    const baseUrl = templateUrl.substring(0, lastSlashIndex + 1);

    // If queueName doesn't have a color suffix, add the active color
    let finalQueueName = queueName;
    if (!queueName.includes('-blue') && !queueName.includes('-green')) {
        // Add active color to queue name (e.g., "prod-compilation-queue" -> "prod-compilation-queue-blue")
        finalQueueName = queueName.replace('.fifo', '') + `-${activeColor}`;
    }

    // Ensure queue name has .fifo suffix (all queues in this system are FIFO)
    const fifoQueueName = finalQueueName.endsWith('.fifo') ? finalQueueName : finalQueueName + '.fifo';

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
                    const activeColor = await getActiveColor();
                    const queueUrl = buildQueueUrl(queueName, activeColor);
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
                    // Fallback to colored queue if no queueName specified
                    const queueUrl = await getColoredQueueUrl();
                    const result = {
                        type: 'queue',
                        target: queueUrl,
                        environment: item.environment?.S || ''
                    };
                    // Cache the result
                    routingCache.set(cacheKey, result);
                    console.info(`Compiler ${compilerId} routed to colored queue (no queueName in DynamoDB)`);
                    console.info(`Routing lookup complete for compiler: ${compilerId}`);
                    return result;
                }
            }
        }

        // No routing found, use colored queue
        console.info(`No routing found for compiler ${compilerId}, using colored queue`);
        const queueUrl = await getColoredQueueUrl();
        const result = {
            type: 'queue',
            target: queueUrl,
            environment: 'unknown'
        };
        // Cache the result
        routingCache.set(cacheKey, result);
        console.info(`Routing lookup complete for compiler: ${compilerId}, using colored queue`);
        return result;

    } catch (error) {
        // On any error, fall back to colored queue
        console.warn(`Failed to lookup routing for compiler ${compilerId}:`, error);
        const queueUrl = await getColoredQueueUrl();
        return {
            type: 'queue',
            target: queueUrl,
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
