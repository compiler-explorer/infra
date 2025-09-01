const {lookupCompilerRouting, sendToSqs} = require('./lib/routing');
const {
    subscribePersistent,
    waitForCompilationResultPersistent,
    getPersistentWebSocket,
} = require('./lib/websocket-client');
const {forwardToEnvironmentUrl} = require('./lib/http-forwarder');
const {
    generateGuid,
    extractCompilerId,
    isCmakeRequest,
    createErrorResponse,
    createSuccessResponse,
} = require('./lib/utils');

// Environment variables
const TIMEOUT_SECONDS = parseInt(process.env.TIMEOUT_SECONDS || '60', 10);
// const WEBSOCKET_URL = process.env.WEBSOCKET_URL || ''; // Currently unused, kept for future use

// Graceful shutdown handler for persistent WebSocket
process.on('SIGTERM', () => {
    console.info('SIGTERM received, closing persistent WebSocket...');
    const wsManager = getPersistentWebSocket();
    if (wsManager) {
        wsManager.close();
    }
});

process.on('SIGINT', () => {
    console.info('SIGINT received, closing persistent WebSocket...');
    const wsManager = getPersistentWebSocket();
    if (wsManager) {
        wsManager.close();
    }
});

/**
 * Main Lambda handler for compilation requests
 * Handles ALB requests for /api/compilers/{compiler_id}/compile and /api/compilers/{compiler_id}/cmake
 */
exports.handler = async event => {
    try {
        // Generate unique GUID for this request immediately
        const guid = generateGuid();

        // Start WebSocket subscription as early as possible to minimize race conditions
        try {
            await subscribePersistent(guid);

            // Add small delay to ensure subscription is processed before sending to SQS
            await new Promise(resolve => setTimeout(resolve, 50));
        } catch (error) {
            console.error('Failed to subscribe to WebSocket:', error);
            return createErrorResponse(500, `Failed to setup result subscription: ${error.message}`);
        }

        // Parse ALB request
        const path = event.path || '';
        const method = event.httpMethod || '';
        const body = event.isBase64Encoded ? Buffer.from(event.body, 'base64').toString('utf8') : event.body || '';
        const headers = event.headers || {};
        const queryStringParameters = event.queryStringParameters || {};

        // Validate request method
        if (method !== 'POST') {
            return createErrorResponse(405, 'Method not allowed');
        }

        // Extract compiler ID from path
        const compilerId = extractCompilerId(path);
        if (!compilerId) {
            return createErrorResponse(400, 'Invalid path: compiler ID not found');
        }

        // Check if this is a cmake request
        const isCmake = isCmakeRequest(path);

        // Determine routing strategy for this compiler
        const routingInfo = await lookupCompilerRouting(compilerId);

        if (routingInfo.type === 'url') {
            // Direct URL forwarding - WebSocket subscription not needed, send unsubscribe
            const wsManager = getPersistentWebSocket();
            if (wsManager && wsManager.ws && wsManager.ws.readyState === 1) {
                // WebSocket.OPEN = 1
                console.info(`WebSocket unsubscribe sent for GUID: ${guid} (URL routing)`);
                wsManager.ws.send(`unsubscribe: ${guid}`);
            }

            try {
                const response = await forwardToEnvironmentUrl(compilerId, routingInfo.target, body, isCmake, headers);

                // Create ALB-compatible response
                const responseHeaders = response.headers || {};
                // Ensure CORS headers are present
                responseHeaders['Access-Control-Allow-Origin'] = '*';
                responseHeaders['Access-Control-Allow-Methods'] = 'POST';
                responseHeaders['Access-Control-Allow-Headers'] = 'Content-Type, Accept';

                return {
                    statusCode: response.statusCode || 200,
                    headers: responseHeaders,
                    body: typeof response.body === 'string' ? response.body : JSON.stringify(response.body),
                };
            } catch (error) {
                console.error('URL forwarding error:', error);
                return createErrorResponse(500, `Failed to forward request: ${error.message}`);
            }
        }

        // Queue-based routing - WebSocket subscription already completed at start
        const queueUrl = routingInfo.target;

        // Create result waiting promise (but don't await it yet)
        let resultPromise = null;

        try {
            // Now send request to SQS queue with headers
            await sendToSqs(guid, compilerId, body, isCmake, headers, queryStringParameters, queueUrl);

            // Only start waiting for result after SQS send succeeds
            resultPromise = waitForCompilationResultPersistent(guid, TIMEOUT_SECONDS);

            // Wait for compilation result via the already-subscribed WebSocket
            const result = await resultPromise;

            // Get Accept header for response formatting
            const filterAnsi = queryStringParameters.filterAnsi && queryStringParameters.filterAnsi === 'true';
            return createSuccessResponse(result, filterAnsi, headers.accept || headers.Accept || '');
        } catch (error) {
            // Handle both SQS errors and compilation result errors
            if (!resultPromise) {
                // Error occurred before creating result promise (likely SQS error)
                console.error('SQS error:', error);
                return createErrorResponse(500, `Failed to queue compilation request: ${error.message}`);
            } else if (error.message.includes('No response received')) {
                console.error('Timeout waiting for compilation result:', error);
                return createErrorResponse(408, `Compilation timeout: ${error.message}`);
            } else {
                console.error('Unexpected error during compilation:', error);
                return createErrorResponse(500, `Failed to complete compilation: ${error.message}`);
            }
        }
    } catch (error) {
        console.error('Unexpected error in lambda_handler:', error);
        return createErrorResponse(500, `Internal server error: ${error.message}`);
    }
};
