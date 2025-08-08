const { lookupCompilerRouting, sendToSqs } = require('./lib/routing');
const { subscribePersistent, waitForCompilationResultPersistent, getPersistentWebSocket } = require('./lib/websocket-client');
const { forwardToEnvironmentUrl } = require('./lib/http-forwarder');
const { generateGuid, extractCompilerId, isCmakeRequest, createErrorResponse, createSuccessResponse } = require('./lib/utils');

// Environment variables
const TIMEOUT_SECONDS = parseInt(process.env.TIMEOUT_SECONDS || '60', 10);
const WEBSOCKET_URL = process.env.WEBSOCKET_URL || '';

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
exports.handler = async (event, context) => {
    try {
        // Parse ALB request
        const path = event.path || '';
        const method = event.httpMethod || '';
        const body = event.body || '';
        const headers = event.headers || {};

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

        // Generate unique GUID for this request
        const guid = generateGuid();

        // Determine routing strategy for this compiler
        const routingInfo = await lookupCompilerRouting(compilerId);

        if (routingInfo.type === 'url') {
            // Direct URL forwarding - no WebSocket needed
            try {
                const response = await forwardToEnvironmentUrl(
                    compilerId,
                    routingInfo.target,
                    body,
                    isCmake,
                    headers
                );

                // Create ALB-compatible response
                const responseHeaders = response.headers || {};
                // Ensure CORS headers are present
                responseHeaders['Access-Control-Allow-Origin'] = '*';
                responseHeaders['Access-Control-Allow-Methods'] = 'POST';
                responseHeaders['Access-Control-Allow-Headers'] = 'Content-Type, Accept';

                return {
                    statusCode: response.statusCode || 200,
                    headers: responseHeaders,
                    body: typeof response.body === 'string' ? response.body : JSON.stringify(response.body)
                };

            } catch (error) {
                console.error('URL forwarding error:', error);
                return createErrorResponse(500, `Failed to forward request: ${error.message}`);
            }
        }

        // Queue-based routing - use persistent WebSocket
        const queueUrl = routingInfo.target;

        // First, ensure WebSocket is connected and subscribe to the GUID
        // This must happen BEFORE sending to SQS to avoid race conditions
        const subscribeStart = Date.now();
        try {
            await subscribePersistent(guid);
            const subscribeTime = Date.now() - subscribeStart;
            console.info(`Lambda timing: WebSocket subscribed in ${subscribeTime}ms`);

            // Add small delay to ensure subscription is processed before sending to SQS
            await new Promise(resolve => setTimeout(resolve, 100));
            console.info('Lambda timing: fixed delay completed (100ms)');
        } catch (error) {
            console.error('Failed to subscribe to WebSocket:', error);
            return createErrorResponse(500, `Failed to setup result subscription: ${error.message}`);
        }

        // Create result waiting promise (but don't await it yet)
        const resultPromise = waitForCompilationResultPersistent(guid, TIMEOUT_SECONDS);

        // Now send request to SQS queue with headers
        const sqsStart = Date.now();
        try {
            await sendToSqs(guid, compilerId, body, isCmake, headers, queueUrl);
            const sqsTime = Date.now() - sqsStart;
            console.info(`Lambda timing: SQS queuing completed in ${sqsTime}ms`);
        } catch (error) {
            console.error('SQS error:', error);
            return createErrorResponse(500, `Failed to queue compilation request: ${error.message}`);
        }

        // Wait for compilation result via the already-subscribed WebSocket
        const resultStart = Date.now();
        try {
            const result = await resultPromise;
            const resultTime = Date.now() - resultStart;
            console.info(`Lambda timing: result received in ${resultTime}ms`);

            // Get Accept header for response formatting
            const responseStart = Date.now();
            const response = createSuccessResponse(result, headers.accept || headers.Accept || '');
            const responseTime = Date.now() - responseStart;
            console.info(`Lambda timing: response formatted in ${responseTime}ms`);
            return response;

        } catch (error) {
            console.error('Timeout or error waiting for compilation result:', error);

            if (error.message.includes('No response received')) {
                return createErrorResponse(408, `Compilation timeout: ${error.message}`);
            }
            return createErrorResponse(500, `Failed to receive compilation result: ${error.message}`);
        }

    } catch (error) {
        console.error('Unexpected error in lambda_handler:', error);
        return createErrorResponse(500, `Internal server error: ${error.message}`);
    }
};
