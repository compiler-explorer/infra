const WebSocket = require('ws');

// Environment variables
const WEBSOCKET_URL = process.env.WEBSOCKET_URL || '';
const RETRY_COUNT = parseInt(process.env.RETRY_COUNT || '1', 10);

// Exponential backoff for retry strategy
function calculateBackoffDelay(attempt, baseDelay = 500) {
    // Exponential backoff with jitter: 500ms, 1000ms, 2000ms, etc.
    const exponentialDelay = baseDelay * Math.pow(2, attempt);
    // Add random jitter (±20%) to prevent thundering herd
    const jitter = exponentialDelay * 0.2 * (Math.random() - 0.5);
    return Math.min(exponentialDelay + jitter, 5000); // Cap at 5 seconds
}

// WebSocket connection options for performance
const WS_OPTIONS = {
    perMessageDeflate: {
        // Enable compression for large compilation results
        zlibDeflateOptions: {
            level: 1, // Fast compression
        },
        threshold: 1024, // Only compress messages > 1KB
    },
    // Optimize for low latency
    handshakeTimeout: 2000, // Reduced from default 5000ms
    // Enable TCP keepalive
    keepAlive: true,
    keepAliveInitialDelay: 300000, // 5 minutes
};

/**
 * WebSocket client for receiving compilation results
 */
class WebSocketClient {
    constructor(url, guid) {
        this.url = url;
        this.guid = guid;
        this.ws = null;
        this.result = null;
        this.connected = false;
        this.error = null;
        this.resultPromise = null;
        this.resultResolver = null;
        this.resultRejecter = null;
    }

    connect() {
        const connectStart = Date.now();
        return new Promise((resolve, reject) => {
            if (!this.url) {
                reject(new Error('WEBSOCKET_URL environment variable not set'));
                return;
            }

            this.ws = new WebSocket(this.url, [], WS_OPTIONS);


            this.ws.on('message', (data) => {
                // Use setImmediate for non-blocking JSON parsing of large messages
                setImmediate(() => {
                    try {
                        const message = JSON.parse(data.toString());
                        const messageGuid = message.guid;

                        if (messageGuid === this.guid) {
                            const totalTime = Date.now() - connectStart;
                            console.info(`WebSocket timing: received result for ${this.guid} after ${totalTime}ms`);
                            // The entire message IS the result
                            this.result = message;

                            // Immediately resolve any waiting promises
                            if (this.resultResolver) {
                                this.resultResolver(message);
                                this.resultResolver = null;
                                this.resultRejecter = null;
                            }

                            this.ws.close();
                        }
                    } catch (error) {
                        console.warn(`Received invalid JSON message: ${data.toString().substring(0, 100)}... Error:`, error);
                        // Reject waiting promise on JSON parse error
                        if (this.resultRejecter) {
                            this.resultRejecter(error);
                            this.resultResolver = null;
                            this.resultRejecter = null;
                        }
                    }
                });
            });

            this.ws.on('error', (error) => {
                const errorTime = Date.now() - connectStart;
                console.error(`WebSocket error for ${this.guid} after ${errorTime}ms:`, error);
                this.error = error;

                // Reject any waiting result promises
                if (this.resultRejecter) {
                    this.resultRejecter(error);
                    this.resultResolver = null;
                    this.resultRejecter = null;
                }

                reject(error);
            });

            this.ws.on('close', () => {
                this.connected = false;
            });

            // Optimized connection timeout - fail fast for better retry behavior
            const connectionTimeout = setTimeout(() => {
                if (!this.connected) {
                    const timeoutDuration = Date.now() - connectStart;
                    console.warn(`WebSocket connection timeout after ${timeoutDuration}ms`);
                    this.ws.close();
                    reject(new Error('WebSocket connection timeout'));
                }
            }, 3000); // Reduced from 5000ms to 3000ms

            // Clear timeout when connection succeeds
            this.ws.on('open', () => {
                clearTimeout(connectionTimeout);
                const connectDuration = Date.now() - connectStart;
                console.info(`WebSocket timing: connection established in ${connectDuration}ms`);
                this.connected = true;
                // Subscribe to messages for this GUID
                const subscribeMsg = `subscribe: ${this.guid}`;
                this.ws.send(subscribeMsg);
                resolve();
            });
        });
    }

    waitForResult(timeout) {
        // If we already have the result, return immediately
        if (this.result !== null) {
            return Promise.resolve(this.result);
        }

        // If there was an error, reject immediately
        if (this.error) {
            return Promise.reject(this.error);
        }

        // Create a promise that will be resolved by the message handler
        return new Promise((resolve, reject) => {
            this.resultResolver = resolve;
            this.resultRejecter = reject;

            // Set up timeout
            const timeoutId = setTimeout(() => {
                if (this.resultRejecter) {
                    this.resultRejecter(new Error(`No response received within ${timeout} seconds`));
                    this.resultResolver = null;
                    this.resultRejecter = null;
                    this.ws.close();
                }
            }, timeout * 1000);

            // Clear timeout when promise resolves/rejects
            const originalResolver = this.resultResolver;
            const originalRejecter = this.resultRejecter;

            this.resultResolver = (result) => {
                clearTimeout(timeoutId);
                originalResolver(result);
            };

            this.resultRejecter = (error) => {
                clearTimeout(timeoutId);
                originalRejecter(error);
            };
        });
    }

    close() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.close();
        }
    }
}

/**
 * Wait for compilation result via WebSocket with retry logic
 */
async function waitForCompilationResult(guid, timeout) {
    const overallStart = Date.now();
    let lastError = null;

    for (let attempt = 0; attempt <= RETRY_COUNT; attempt++) {
        const attemptStart = Date.now();
        try {
            console.info(`WebSocket timing: attempt ${attempt + 1}/${RETRY_COUNT + 1} starting`);
            const client = new WebSocketClient(WEBSOCKET_URL, guid);
            await client.connect();
            const result = await client.waitForResult(timeout);
            const totalDuration = Date.now() - overallStart;
            console.info(`WebSocket timing: compilation completed successfully after ${totalDuration}ms total (${attempt + 1} attempts)`);
            return result;
        } catch (error) {
            const attemptDuration = Date.now() - attemptStart;
            console.warn(`WebSocket timing: attempt ${attempt + 1} failed after ${attemptDuration}ms:`, error.message);
            lastError = error;
            if (attempt < RETRY_COUNT) {
                const backoffDelay = calculateBackoffDelay(attempt);
                console.info(`WebSocket timing: retrying in ${Math.round(backoffDelay)}ms... (exponential backoff)`);
                await new Promise(resolve => setTimeout(resolve, backoffDelay));
            }
        }
    }

    const totalDuration = Date.now() - overallStart;
    console.error(`WebSocket timing: all attempts failed after ${totalDuration}ms`);
    throw lastError || new Error('All WebSocket attempts failed');
}

module.exports = {
    WebSocketClient,
    waitForCompilationResult
};
