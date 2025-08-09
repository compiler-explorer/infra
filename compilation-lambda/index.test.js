// Mock modules before importing them
jest.mock('./lib/aws-clients');
jest.mock('./lib/routing');
jest.mock('./lib/websocket-client');
jest.mock('./lib/http-forwarder');
jest.mock('./lib/utils', () => ({
    ...jest.requireActual('./lib/utils'),
    generateGuid: () => 'test-uuid-1234'
}));

// Set environment variables before importing the handler
process.env.ENVIRONMENT_NAME = 'test';
process.env.SQS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo';
process.env.WEBSOCKET_URL = 'wss://test.example.com/websocket';
process.env.TIMEOUT_SECONDS = '1';

// Import the handler after mocks are set up
const { handler } = require('./index');

// Import the mocked modules to set up expectations
const { lookupCompilerRouting, sendToSqs } = require('./lib/routing');
const { subscribePersistent, waitForCompilationResultPersistent, getPersistentWebSocket } = require('./lib/websocket-client');
const { forwardToEnvironmentUrl } = require('./lib/http-forwarder');

describe('Compilation Lambda Handler', () => {
    let originalConsoleError;
    
    beforeAll(() => {
        // Suppress console.error during tests since we're testing error conditions
        originalConsoleError = console.error;
        console.error = jest.fn();
    });
    
    afterAll(() => {
        // Restore original console.error
        console.error = originalConsoleError;
    });
    
    beforeEach(() => {
        jest.clearAllMocks();
        // Clear the console.error mock for each test
        console.error.mockClear();
    });

    describe('Request Validation', () => {
        test('should reject non-POST methods', async () => {
            const event = {
                httpMethod: 'GET',
                path: '/api/compiler/gcc/compile'
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(405);
            expect(JSON.parse(response.body).error).toBe('Method not allowed');
        });

        test('should reject invalid paths', async () => {
            const event = {
                httpMethod: 'POST',
                path: '/invalid/path'
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(400);
            expect(JSON.parse(response.body).error).toBe('Invalid path: compiler ID not found');
        });
    });

    describe('URL Forwarding', () => {
        test('should use URL forwarding when routing returns URL config', async () => {
            // Mock routing to return URL config
            lookupCompilerRouting.mockResolvedValue({
                type: 'url',
                target: 'https://example.com/api/compiler/gcc/compile',
                environment: 'test'
            });

            // Mock HTTP forwarding
            forwardToEnvironmentUrl.mockResolvedValue({
                statusCode: 200,
                headers: { 'content-type': 'application/json' },
                body: { asm: [{ text: 'mov eax, 0' }] }
            });

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(200);
            expect(lookupCompilerRouting).toHaveBeenCalledWith('gcc');
            expect(forwardToEnvironmentUrl).toHaveBeenCalledWith(
                'gcc',
                'https://example.com/api/compiler/gcc/compile',
                '{"source": "int main() {}"}',
                false,
                { 'content-type': 'application/json' }
            );
            expect(sendToSqs).not.toHaveBeenCalled();
        });

        test('should handle URL forwarding failure', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'url',
                target: 'https://example.com/api/compiler/gcc/compile',
                environment: 'test'
            });

            forwardToEnvironmentUrl.mockRejectedValue(new Error('Network error'));

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(500);
            expect(JSON.parse(response.body).error).toContain('Failed to forward request');
        });
    });

    describe('Queue Routing', () => {
        test('should handle WebSocket connection failure gracefully', async () => {
            // Mock routing to return queue config
            lookupCompilerRouting.mockResolvedValue({
                type: 'queue',
                target: 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo',
                environment: 'test'
            });

            // Mock WebSocket subscription to fail
            subscribePersistent.mockRejectedValue(new Error('Connection failed'));

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(500);
            expect(JSON.parse(response.body).error).toContain('Failed to setup result subscription');
        });

        test('should handle successful queue routing', async () => {
            // Mock routing to return queue config
            lookupCompilerRouting.mockResolvedValue({
                type: 'queue',
                target: 'https://sqs.us-east-1.amazonaws.com/123456789/custom-queue.fifo',
                environment: 'test'
            });

            // Mock SQS sending
            sendToSqs.mockResolvedValue();

            // Mock WebSocket with successful result
            subscribePersistent.mockResolvedValue();
            waitForCompilationResultPersistent.mockResolvedValue({
                guid: 'test-uuid-1234',
                asm: [{ text: 'mov eax, 0' }],
                code: 0
            });

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(200);
            expect(lookupCompilerRouting).toHaveBeenCalledWith('gcc');
            expect(sendToSqs).toHaveBeenCalledWith(
                'test-uuid-1234',
                'gcc',
                '{"source": "int main() {}"}',
                false,
                { 'content-type': 'application/json' },
                'https://sqs.us-east-1.amazonaws.com/123456789/custom-queue.fifo'
            );
            expect(waitForCompilationResultPersistent).toHaveBeenCalledWith('test-uuid-1234', 1); // TIMEOUT_SECONDS
        });
    });

    describe('Path Parsing', () => {
        test('should extract compiler ID from production path', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'url',
                target: 'https://example.com/api/compiler/gcc-12/compile',
                environment: 'test'
            });

            forwardToEnvironmentUrl.mockResolvedValue({
                statusCode: 200,
                headers: {},
                body: 'success'
            });

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc-12/compile',
                body: 'int main() {}',
                headers: {}
            };

            await handler(event, {});

            expect(lookupCompilerRouting).toHaveBeenCalledWith('gcc-12');
            expect(forwardToEnvironmentUrl).toHaveBeenCalledWith(
                'gcc-12',
                'https://example.com/api/compiler/gcc-12/compile',
                'int main() {}',
                false,
                {}
            );
        });

        test('should extract compiler ID from environment-specific path', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'url',
                target: 'https://example.com/api/compiler/clang-trunk/compile',
                environment: 'test'
            });

            forwardToEnvironmentUrl.mockResolvedValue({
                statusCode: 200,
                headers: {},
                body: 'success'
            });

            const event = {
                httpMethod: 'POST',
                path: '/beta/api/compiler/clang-trunk/compile',
                body: 'int main() {}',
                headers: {}
            };

            await handler(event, {});

            expect(lookupCompilerRouting).toHaveBeenCalledWith('clang-trunk');
        });

        test('should detect cmake requests', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'url',
                target: 'https://example.com/api/compiler/gcc/compile',
                environment: 'test'
            });

            forwardToEnvironmentUrl.mockResolvedValue({
                statusCode: 200,
                headers: {},
                body: 'success'
            });

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/cmake',
                body: 'project(test)',
                headers: {}
            };

            await handler(event, {});

            // Should pass isCmake=true to forwardToEnvironmentUrl
            expect(forwardToEnvironmentUrl).toHaveBeenCalledWith(
                'gcc',
                'https://example.com/api/compiler/gcc/compile',
                'project(test)',
                true, // isCmake should be true
                {}
            );
        });
    });

    describe('Error Handling', () => {
        test('should handle routing lookup errors gracefully', async () => {
            lookupCompilerRouting.mockRejectedValue(new Error('DynamoDB error'));

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/unknown/compile',
                body: 'int main() {}',
                headers: {}
            };

            const response = await handler(event, {});

            // Should still try to handle the request, but the routing lookup failed
            // The lookupCompilerRouting function should handle errors internally
            // and return a default fallback, but if it throws, we get a 500
            expect(response.statusCode).toBe(500);
        });

        test('should handle SQS send failure', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'queue',
                target: 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo',
                environment: 'test'
            });

            subscribePersistent.mockResolvedValue();

            sendToSqs.mockRejectedValue(new Error('SQS error'));

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(500);
            expect(JSON.parse(response.body).error).toContain('Failed to queue compilation request');
        });

        test('should handle compilation timeout', async () => {
            lookupCompilerRouting.mockResolvedValue({
                type: 'queue',
                target: 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo',
                environment: 'test'
            });

            sendToSqs.mockResolvedValue();

            subscribePersistent.mockResolvedValue();
            waitForCompilationResultPersistent.mockRejectedValue(new Error('No response received within 1 seconds'));

            const event = {
                httpMethod: 'POST',
                path: '/api/compiler/gcc/compile',
                body: '{"source": "int main() {}"}',
                headers: { 'content-type': 'application/json' }
            };

            const response = await handler(event, {});

            expect(response.statusCode).toBe(408);
            expect(JSON.parse(response.body).error).toContain('Compilation timeout');
        });
    });
});
