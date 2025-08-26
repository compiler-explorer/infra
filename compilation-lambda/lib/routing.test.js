const { buildQueueUrl } = require('./routing');

describe('buildQueueUrl', () => {
    const originalEnv = process.env;

    beforeEach(() => {
        // Reset environment variables before each test
        process.env = { ...originalEnv };
    });

    afterAll(() => {
        // Restore original environment
        process.env = originalEnv;
    });

    describe('with color-specific queue URLs configured', () => {
        beforeEach(() => {
            process.env.SQS_QUEUE_URL_BLUE = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-blue.fifo';
            process.env.SQS_QUEUE_URL_GREEN = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-green.fifo';
        });

        test('builds queue URL for blue active color with color-agnostic queue name', () => {
            const queueUrl = buildQueueUrl('prod-compilation-queue', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/prod-compilation-queue-blue.fifo');
        });

        test('builds queue URL for green active color with color-agnostic queue name', () => {
            const queueUrl = buildQueueUrl('prod-compilation-queue', 'green');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/prod-compilation-queue-green.fifo');
        });

        test('preserves existing blue color in queue name when active is blue', () => {
            const queueUrl = buildQueueUrl('staging-compilation-queue-blue', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/staging-compilation-queue-blue.fifo');
        });

        test('preserves existing green color in queue name when active is green', () => {
            const queueUrl = buildQueueUrl('staging-compilation-queue-green', 'green');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/staging-compilation-queue-green.fifo');
        });

        test('preserves existing color even if different from active color', () => {
            // This tests that if a queue explicitly specifies a color, we don't override it
            const queueUrl = buildQueueUrl('staging-compilation-queue-green', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/staging-compilation-queue-green.fifo');
        });

        test('handles queue names with .fifo suffix', () => {
            const queueUrl = buildQueueUrl('prod-compilation-queue.fifo', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/prod-compilation-queue-blue.fifo');
        });

        test('handles queue names with color and .fifo suffix', () => {
            const queueUrl = buildQueueUrl('prod-compilation-queue-blue.fifo', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/prod-compilation-queue-blue.fifo');
        });

        test('adds active color to custom queue names', () => {
            const queueUrl = buildQueueUrl('special-compiler-queue', 'green');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/special-compiler-queue-green.fifo');
        });
    });

    describe('error handling', () => {
        test('throws error when blue queue URL not configured for blue active color', () => {
            process.env.SQS_QUEUE_URL_GREEN = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-green.fifo';
            delete process.env.SQS_QUEUE_URL_BLUE;

            expect(() => buildQueueUrl('test-queue', 'blue')).toThrow(
                "Queue URL for active color 'blue' not configured in environment variables"
            );
        });

        test('throws error when green queue URL not configured for green active color', () => {
            process.env.SQS_QUEUE_URL_BLUE = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-blue.fifo';
            delete process.env.SQS_QUEUE_URL_GREEN;

            expect(() => buildQueueUrl('test-queue', 'green')).toThrow(
                "Queue URL for active color 'green' not configured in environment variables"
            );
        });

        test('throws error for invalid queue URL format', () => {
            process.env.SQS_QUEUE_URL_BLUE = 'invalid-url-without-slash';
            process.env.SQS_QUEUE_URL_GREEN = 'invalid-url-without-slash';

            expect(() => buildQueueUrl('test-queue', 'blue')).toThrow('Invalid queue URL format');
        });
    });

    describe('edge cases', () => {
        beforeEach(() => {
            process.env.SQS_QUEUE_URL_BLUE = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-blue.fifo';
            process.env.SQS_QUEUE_URL_GREEN = 'https://sqs.us-east-1.amazonaws.com/123456789012/beta-compilation-queue-green.fifo';
        });

        test('handles queue names with multiple hyphens', () => {
            const queueUrl = buildQueueUrl('my-special-test-queue', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/my-special-test-queue-blue.fifo');
        });

        test('handles queue names that contain "blue" but not as color suffix', () => {
            const queueUrl = buildQueueUrl('bluetooth-processor-queue', 'green');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/bluetooth-processor-queue-green.fifo');
        });

        test('handles queue names that contain "green" but not as color suffix', () => {
            const queueUrl = buildQueueUrl('greenfield-project-queue', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/greenfield-project-queue-blue.fifo');
        });

        test('handles empty queue name', () => {
            const queueUrl = buildQueueUrl('', 'blue');
            expect(queueUrl).toBe('https://sqs.us-east-1.amazonaws.com/123456789012/-blue.fifo');
        });
    });
});