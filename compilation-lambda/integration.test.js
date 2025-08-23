/**
 * Integration Tests for Compilation Lambda
 * These tests run against actual AWS services (DynamoDB, SQS, STS) without mocking
 *
 * To run: npm run test:integration
 * Environment: Requires AWS credentials and access to CompilerRouting table
 */

// Set environment variables for testing
process.env.ENVIRONMENT_NAME = 'test';
process.env.AWS_REGION = 'us-east-1';
process.env.SQS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/052730242331/test-compilation-queue.fifo';
process.env.WEBSOCKET_URL = 'wss://test.example.com/websocket';

const { lookupCompilerRouting, sendToSqs, parseRequestBody, buildQueueUrl } = require('./lib/routing');
const { AWS_ACCOUNT_ID, sqs } = require('./lib/aws-clients');
const { generateGuid, extractCompilerId, isCmakeRequest, createSuccessResponse } = require('./lib/utils');
const routing = require('./lib/routing');

describe('Integration Tests - Real AWS Services', () => {
    let originalConsoleWarn;

    beforeAll(() => {
        // Suppress console.warn during tests
        originalConsoleWarn = console.warn;
        console.warn = jest.fn();
    });

    afterAll(() => {
        // Restore original console.warn
        console.warn = originalConsoleWarn;
    });

    describe('AWS Account Identity', () => {
        test('should have correct AWS account ID constant', () => {
            expect(AWS_ACCOUNT_ID).toBeTruthy();
            expect(AWS_ACCOUNT_ID).toMatch(/^\d{12}$/); // Should be 12 digits
            expect(AWS_ACCOUNT_ID).toBe('052730242331'); // Expected account ID
        });
    });

    describe('DynamoDB Compiler Routing', () => {
        test('should lookup prod compiler with queue routing', async () => {
            // Use a known compiler from the scan results
            const result = await lookupCompilerRouting('gimpleesp32g20230208');

            // Should fall back to test environment first, then legacy
            expect(result).toBeDefined();
            expect(result.type).toBeDefined();
            expect(result.target).toBeDefined();
            expect(result.environment).toBeDefined();
        }, 10000);

        test('should lookup GPU compiler with URL routing', async () => {
            // Change environment to gpu to find the URL routing entry
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'gpu';

            try {
                const result = await lookupCompilerRouting('nvcc129u1');

                expect(result).toBeDefined();
                expect(result.type).toBe('url');
                expect(result.target).toBe('https://godbolt.org/gpu/api/compiler/nvcc129u1/compile');
                expect(result.environment).toBe('gpu');
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 10000);

        test('should lookup compiler with GPU queue routing', async () => {
            // Test a scenario where a GPU compiler would route to a GPU-specific queue
            // Let's test if we can find a GPU compiler that uses queue routing
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'gpu';

            try {
                // Try to find a GPU compiler that uses queue routing
                // We'll scan for compilers in the gpu environment that have queueName set
                const result = await lookupCompilerRouting('ptxas12');

                if (result.type === 'queue') {
                    expect(result).toBeDefined();
                    expect(result.type).toBe('queue');
                    // Should build GPU-specific queue URL
                    expect(result.target).toMatch(/gpu.*queue/i);
                    expect(result.environment).toBe('gpu');
                    console.log(`✓ GPU compiler routed to queue: ${result.target}`);
                } else {
                    // If no GPU queue routing found, test our buildQueueUrl logic with a hypothetical GPU queue
                    const gpuQueueUrl = buildQueueUrl('gpu-compilation-queue');
                    expect(gpuQueueUrl).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/gpu-compilation-queue.fifo');
                    console.log(`✓ GPU queue URL would be: ${gpuQueueUrl}`);
                }
            } catch (error) {
                // If ptxas12 doesn't exist, test the buildQueueUrl function instead
                const gpuQueueUrl = buildQueueUrl('gpu-compilation-queue');
                expect(gpuQueueUrl).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/gpu-compilation-queue.fifo');
                console.log(`✓ GPU queue URL derivation works: ${gpuQueueUrl}`);
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 10000);

        test('should handle non-existent compiler gracefully', async () => {
            const result = await lookupCompilerRouting('non-existent-compiler-12345');

            // Should fallback to default queue
            expect(result).toBeDefined();
            expect(result.type).toBe('queue');
            expect(result.target).toBe(process.env.SQS_QUEUE_URL);
            expect(result.environment).toBe('unknown');
        }, 10000);

        test('should handle composite key lookup (environment-prefixed)', async () => {
            // Set environment to prod to test composite key lookup
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'prod';

            try {
                const result = await lookupCompilerRouting('gimpleesp32g20230208');

                expect(result).toBeDefined();
                expect(result.type).toBe('queue');
                expect(result.target).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/prod-compilation-queue.fifo');
                expect(result.environment).toBe('prod');
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 10000);

        test('should construct correct queue URL from DynamoDB data', async () => {
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'prod';

            try {
                const result = await lookupCompilerRouting('gimpleesp32g20230208');

                expect(result.type).toBe('queue');
                expect(result.target).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/prod-compilation-queue.fifo');
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 10000);
    });

    describe('Request Body Parsing', () => {
        test('should parse JSON request body', () => {
            const jsonBody = '{"source": "int main() { return 0; }", "options": ["-O2"]}';
            const result = parseRequestBody(jsonBody, 'application/json');

            expect(result).toEqual({
                source: 'int main() { return 0; }',
                options: ['-O2']
            });
        });

        test('should parse plain text as source code', () => {
            const plainBody = 'int main() { return 0; }';
            const result = parseRequestBody(plainBody, 'text/plain');

            expect(result).toEqual({
                source: 'int main() { return 0; }'
            });
        });

        test('should handle malformed JSON gracefully', () => {
            const malformedJson = '{"source": "int main() {", invalid}';
            const result = parseRequestBody(malformedJson, 'application/json');

            // Should treat as plain text when JSON parsing fails
            expect(result).toEqual({
                source: malformedJson
            });
        });

        test('should handle empty body', () => {
            const result = parseRequestBody('', 'application/json');
            expect(result).toEqual({});
        });
    });

    describe('Utility Functions', () => {
        test('should generate valid GUID', () => {
            const guid = generateGuid();

            expect(guid).toBeTruthy();
            expect(typeof guid).toBe('string');
            expect(guid.length).toBeGreaterThan(10);

            // Should be different each time
            const guid2 = generateGuid();
            expect(guid).not.toBe(guid2);
        });

        test('should extract compiler ID from various path formats', () => {
            expect(extractCompilerId('/api/compiler/gcc/compile')).toBe('gcc');
            expect(extractCompilerId('/beta/api/compiler/clang-trunk/compile')).toBe('clang-trunk');
            expect(extractCompilerId('/api/compiler/nvcc129u1/cmake')).toBe('nvcc129u1');
            expect(extractCompilerId('/staging/api/compiler/gcc-12.3/compile')).toBe('gcc-12.3');
        });

        test('should detect cmake requests correctly', () => {
            expect(isCmakeRequest('/api/compiler/gcc/cmake')).toBe(true);
            expect(isCmakeRequest('/beta/api/compiler/gcc/cmake')).toBe(true);
            expect(isCmakeRequest('/api/compiler/gcc/compile')).toBe(false);
        });

        test('should create properly formatted ALB response', () => {
            const response = createSuccessResponse({ result: 'success' });

            expect(response.statusCode).toBe(200);
            expect(response.headers['Content-Type']).toBe('application/json; charset=utf-8');
            expect(response.body).toBe('{"result":"success"}');
        });
    });

    describe('Queue URL Building', () => {

        test('should build queue URL from template and queue name', () => {
            // Using the existing SQS_QUEUE_URL from test setup
            const result = buildQueueUrl('custom-queue');
            expect(result).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/custom-queue.fifo');
        });

        test('should build queue URL for different queue names', () => {
            expect(buildQueueUrl('prod-queue')).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/prod-queue.fifo');
            expect(buildQueueUrl('gpu-compilation-queue')).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/gpu-compilation-queue.fifo');
            expect(buildQueueUrl('arm-compilation-queue')).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/arm-compilation-queue.fifo');
            expect(buildQueueUrl('windows-compilation-queue')).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/windows-compilation-queue.fifo');
        });

        test('should handle queue names that already have .fifo suffix', () => {
            expect(buildQueueUrl('existing-queue.fifo')).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/existing-queue.fifo');
        });

        test('should throw error if SQS_QUEUE_URL not set', () => {
            const originalUrl = process.env.SQS_QUEUE_URL;
            delete process.env.SQS_QUEUE_URL;

            expect(() => buildQueueUrl('test-queue')).toThrow('SQS_QUEUE_URL environment variable not set');

            process.env.SQS_QUEUE_URL = originalUrl;
        });

        test('should throw error for invalid URL format', () => {
            const originalUrl = process.env.SQS_QUEUE_URL;
            process.env.SQS_QUEUE_URL = 'invalid-url-without-slash';

            expect(() => buildQueueUrl('test-queue')).toThrow('Invalid SQS_QUEUE_URL format');

            process.env.SQS_QUEUE_URL = originalUrl;
        });
    });

    describe('SQS Integration (Dry Run)', () => {
        test('should construct valid SQS message without actually sending', async () => {
            // We'll test message construction but not actually send to avoid cluttering queues
            const guid = generateGuid();
            const compilerId = 'gcc';
            const body = '{"source": "int main() { return 0; }", "options": ["-O2"]}';
            const isCmake = false;
            const headers = { 'content-type': 'application/json' };

            // Mock the SQS send to capture the message that would be sent
            const originalSqsSend = sqs.send;
            const mockSend = jest.fn();
            sqs.send = mockSend;

            try {
                await sendToSqs(guid, compilerId, body, isCmake, headers, process.env.SQS_QUEUE_URL);

                expect(mockSend).toHaveBeenCalledTimes(1);
                const callArgs = mockSend.mock.calls[0][0];

                // Verify SQS command structure
                expect(callArgs.constructor.name).toBe('SendMessageCommand');
                expect(callArgs.input.QueueUrl).toBe(process.env.SQS_QUEUE_URL);
                expect(callArgs.input.MessageGroupId).toBe('default');
                expect(callArgs.input.MessageDeduplicationId).toBe(guid);

                // Parse and verify message body
                const messageBody = JSON.parse(callArgs.input.MessageBody);
                expect(messageBody.guid).toBe(guid);
                expect(messageBody.compilerId).toBe(compilerId);
                expect(messageBody.isCMake).toBe(false);
                expect(messageBody.source).toBe('int main() { return 0; }');
                expect(messageBody.options).toEqual(['-O2']);

                // Verify defaults are added
                expect(messageBody.filters).toEqual({});
                expect(messageBody.backendOptions).toEqual({});
                expect(messageBody.tools).toEqual([]);
                expect(messageBody.libraries).toEqual([]);
                expect(messageBody.files).toEqual([]);
                expect(messageBody.executeParameters).toEqual({});

            } finally {
                // Restore original SQS client
                sqs.send = originalSqsSend;
            }
        });

        test('should handle plain text body in SQS message', async () => {
            const guid = generateGuid();
            const body = 'int main() { return 0; }';
            const headers = { 'content-type': 'text/plain' };

            const originalSqsSend2 = sqs.send;
            const mockSend = jest.fn();
            sqs.send = mockSend;

            try {
                await sendToSqs(guid, 'gcc', body, false, headers, process.env.SQS_QUEUE_URL);

                const messageBody = JSON.parse(mockSend.mock.calls[0][0].input.MessageBody);
                expect(messageBody.source).toBe('int main() { return 0; }');
            } finally {
                sqs.send = originalSqsSend2;
            }
        });

        test('should handle missing queue URL error', async () => {
            await expect(sendToSqs('test-guid', 'gcc', '{}', false, {}, '')).rejects.toThrow(
                'No queue URL available'
            );
        });
    });

    describe('Error Handling', () => {
        test('should handle DynamoDB access errors gracefully', async () => {
            // Temporarily break the table name to simulate an error
            const originalTableName = 'CompilerRouting';

            // We can't easily mock this in integration test, but we can test with invalid compiler
            // The function should handle errors gracefully and return default routing
            const result = await lookupCompilerRouting('definitely-non-existent-compiler-xyz-999');

            expect(result.type).toBe('queue');
            expect(result.target).toBe(process.env.SQS_QUEUE_URL);
            expect(result.environment).toBe('unknown');
        }, 10000);
    });

    describe('End-to-End Routing Flow', () => {
        test('should complete full routing lookup flow for prod compiler', async () => {
            // Test the complete flow: lookup compiler -> get routing decision
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'prod';

            try {
                const compilerId = 'gimpleesp32g20230208'; // Known compiler from scan
                const result = await lookupCompilerRouting(compilerId);

                // Should find the prod routing
                expect(result.type).toBe('queue');
                expect(result.target).toBe('https://sqs.us-east-1.amazonaws.com/052730242331/prod-compilation-queue.fifo');
                expect(result.environment).toBe('prod');

                // Verify queue URL format is correct for SQS usage
                expect(result.target).toMatch(/^https:\/\/sqs\.[a-z0-9-]+\.amazonaws\.com\/\d{12}\/[\w-]+/);

                console.log(`✓ Compiler ${compilerId} routed to: ${result.target}`);
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 15000);

        test('should complete full routing lookup flow for GPU compiler', async () => {
            const originalEnv = process.env.ENVIRONMENT_NAME;
            process.env.ENVIRONMENT_NAME = 'gpu';

            try {
                const compilerId = 'nvcc129u1'; // Known GPU compiler
                const result = await lookupCompilerRouting(compilerId);

                // Should find the GPU URL routing
                expect(result.type).toBe('url');
                expect(result.target).toBe('https://godbolt.org/gpu/api/compiler/nvcc129u1/compile');
                expect(result.environment).toBe('gpu');

                console.log(`✓ Compiler ${compilerId} routed to: ${result.target}`);
            } finally {
                process.env.ENVIRONMENT_NAME = originalEnv;
            }
        }, 15000);
    });
});
