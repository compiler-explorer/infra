const { lookupCompilerRouting, sendToSqs } = require('./lib/routing');
const { WebSocketClient } = require('./lib/websocket-client');
const { forwardToEnvironmentUrl } = require('./lib/http-forwarder');
const { generateGuid, extractCompilerId, isCmakeRequest, createErrorResponse, createSuccessResponse } = require('./lib/utils');

// Environment variables
const TIMEOUT_SECONDS = parseInt(process.env.TIMEOUT_SECONDS || '60', 10);
const WEBSOCKET_URL = process.env.WEBSOCKET_URL || '';

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

        // Start WebSocket connection and routing lookup in parallel for queue-based routing
        // This saves time by overlapping the network operations
        const routingPromise = lookupCompilerRouting(compilerId);
        const wsConnectionPromise = (async () => {
            try {
                const wsClient = new WebSocketClient(WEBSOCKET_URL, guid);
                await wsClient.connect();
                return wsClient;
            } catch (error) {
                // Don't throw here - let routing decision determine if we need WebSocket
                console.warn('WebSocket connection failed during parallel setup:', error);
                return null;
            }
        })();

        // Wait for routing decision
        const routingInfo = await routingPromise;

        if (routingInfo.type === 'url') {
            // Direct URL forwarding - cancel WebSocket if it's still connecting
            wsConnectionPromise.then(ws => ws && ws.close()).catch(() => {});
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

        // Queue-based routing - use the WebSocket connection we started in parallel
        const queueUrl = routingInfo.target;

        // Wait for the WebSocket connection we started in parallel
        let wsClient;
        try {
            wsClient = await wsConnectionPromise;
            if (!wsClient) {
                // WebSocket connection failed, try once more synchronously
                wsClient = new WebSocketClient(WEBSOCKET_URL, guid);
                await wsClient.connect();
            }

            // Small delay to ensure subscription is processed
            await new Promise(resolve => setTimeout(resolve, 100));

        } catch (error) {
            console.error('Failed to setup WebSocket subscription:', error);
            return createErrorResponse(500, `Failed to setup result subscription: ${error.message}`);
        }

        // Now send request to SQS queue with headers
        try {
            await sendToSqs(guid, compilerId, body, isCmake, headers, queueUrl);
        } catch (error) {
            console.error('SQS error:', error);
            wsClient.close();
            return createErrorResponse(500, `Failed to queue compilation request: ${error.message}`);
        }

        // Wait for compilation result via the already-connected WebSocket
        try {
            const result = await wsClient.waitForResult(TIMEOUT_SECONDS);

            // Get Accept header for response formatting
            const acceptHeader = headers.accept || headers.Accept || '';
            return createSuccessResponse(result, acceptHeader);

        } catch (error) {
            console.error('Timeout or error waiting for compilation result:', error);
            wsClient.close();

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
