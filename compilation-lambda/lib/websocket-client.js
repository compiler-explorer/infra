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
    perMessageDeflate: false,  // Disable compression for faster connection
    handshakeTimeout: 2000,    // 2 seconds - balanced for cold starts
    keepAlive: true,
    keepAliveInitialDelay: 300000, // 5 minutes
    rejectUnauthorized: true,
    headers: {
        'Connection': 'Upgrade',
        'Upgrade': 'websocket',
        'User-Agent': 'CE-Lambda/1.0'
    }
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
                // Synchronous JSON parsing for minimal latency
                try {
                    const dataString = data.toString();
                    const message = JSON.parse(dataString);
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

            // Aggressive connection timeout for fast failure detection
            const connectionTimeout = setTimeout(() => {
                if (!this.connected) {
                    const timeoutDuration = Date.now() - connectStart;
                    console.warn(`WebSocket connection timeout after ${timeoutDuration}ms`);
                    this.ws.close();
                    reject(new Error('WebSocket connection timeout'));
                }
            }, 1500); // Aggressive timeout - if connection takes >1.5s, retry immediately

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

/**
 * Persistent WebSocket connection manager
 * Keeps a single WebSocket connection alive for the Lambda lifetime
 */
class PersistentWebSocketManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.connected = false;
        this.connecting = false;
        this.subscriptions = new Map(); // guid -> { resolver, rejecter, timeout }
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
    }

    async ensureConnected() {
        if (this.connected) return;
        if (this.connecting) {
            // Wait for existing connection attempt
            while (this.connecting) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
            return;
        }

        this.connecting = true;
        try {
            await this.connect();
            this.reconnectAttempts = 0;
        } catch (error) {
            this.connecting = false;
            throw error;
        }
        this.connecting = false;
    }

    async connect() {
        const connectStart = Date.now();

        return new Promise((resolve, reject) => {
            if (!this.url) {
                reject(new Error('WEBSOCKET_URL not configured'));
                return;
            }

            this.ws = new WebSocket(this.url, [], WS_OPTIONS);

            this.ws.on('message', (data) => {
                const messageText = data.toString();

                // Check if it's an acknowledgment message (plain text)
                if (messageText.startsWith('subscribed: ') || messageText.startsWith('unsubscribed: ')) {
                    // Acknowledgment messages are handled by the subscribe() method's ackHandler
                    return;
                }

                // Try to parse as JSON for result messages
                try {
                    const message = JSON.parse(messageText);
                    const messageGuid = message.guid;

                    if (messageGuid && this.subscriptions.has(messageGuid)) {
                        const subscription = this.subscriptions.get(messageGuid);
                        clearTimeout(subscription.timeout);
                        subscription.resolver(message);
                        this.subscriptions.delete(messageGuid);

                        // Send unsubscribe command to free server resources
                        if (this.ws.readyState === WebSocket.OPEN) {
                            this.ws.send(`unsubscribe: ${messageGuid}`);
                        }
                    }
                } catch (error) {
                    console.warn('Failed to parse WebSocket message:', messageText.substring(0, 100), '...', error.message);
                }
            });

            this.ws.on('error', (error) => {
                const errorTime = Date.now() - connectStart;
                console.error(`Persistent WebSocket error after ${errorTime}ms:`, error);
                this.connected = false;

                // Reject all pending subscriptions
                for (const [guid, subscription] of this.subscriptions) {
                    clearTimeout(subscription.timeout);
                    subscription.rejecter(error);
                }
                this.subscriptions.clear();

                reject(error);
            });

            this.ws.on('close', () => {
                const closeTime = Date.now() - connectStart;
                console.warn(`Persistent WebSocket closed after ${closeTime}ms`);
                this.connected = false;

                // Reject all pending subscriptions with close error
                for (const [guid, subscription] of this.subscriptions) {
                    clearTimeout(subscription.timeout);
                    subscription.rejecter(new Error('WebSocket connection closed'));
                }
                this.subscriptions.clear();

                // Auto-reconnect for subsequent requests if within attempt limit
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => {
                        if (!this.connected && !this.connecting) {
                            console.info(`Attempting WebSocket reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
                            this.connect().catch(err => console.warn('Reconnect failed:', err));
                        }
                    }, 1000 * this.reconnectAttempts);
                }
            });

            this.ws.on('open', () => {
                const connectDuration = Date.now() - connectStart;
                console.info(`Persistent WebSocket connected in ${connectDuration}ms`);
                this.connected = true;
                resolve();
            });

            // Connection timeout
            setTimeout(() => {
                if (!this.connected) {
                    console.warn('Persistent WebSocket connection timeout');
                    this.ws.close();
                    reject(new Error('Connection timeout'));
                }
            }, 2000);
        });
    }

    async subscribe(guid) {
        await this.ensureConnected();

        if (this.ws.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket not connected');
        }

        // Send subscribe command and wait for acknowledgment
        return new Promise((resolve, reject) => {
            const expectedAck = `subscribed: ${guid}`;

            // Set up acknowledgment listener
            const ackHandler = (data) => {
                const message = data.toString();
                if (message === expectedAck) {
                    this.ws.removeListener('message', ackHandler);
                    clearTimeout(ackTimeout);
                    console.info(`Subscription confirmed for GUID: ${guid}`);
                    resolve();
                }
            };

            // Set up timeout for acknowledgment
            const ackTimeout = setTimeout(() => {
                this.ws.removeListener('message', ackHandler);
                reject(new Error(`Subscription acknowledgment timeout for ${guid}`));
            }, 5000); // 5 second timeout

            this.ws.on('message', ackHandler);

            try {
                this.ws.send(`subscribe: ${guid}`, (err) => {
                    if (err) {
                        this.ws.removeListener('message', ackHandler);
                        clearTimeout(ackTimeout);
                        reject(err);
                    }
                });
            } catch (error) {
                this.ws.removeListener('message', ackHandler);
                clearTimeout(ackTimeout);
                reject(error);
            }
        });
    }

    waitForResult(guid, timeoutSeconds = 60) {
        // This sets up the listener but doesn't send subscribe
        return new Promise((resolve, reject) => {
            // Check if already have result
            if (this.subscriptions.has(guid) && this.subscriptions.get(guid).result) {
                resolve(this.subscriptions.get(guid).result);
                this.subscriptions.delete(guid);
                return;
            }

            // Set up timeout
            const timeout = setTimeout(() => {
                this.subscriptions.delete(guid);
                // Send unsubscribe on timeout
                if (this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(`unsubscribe: ${guid}`);
                }
                reject(new Error(`No response received within ${timeoutSeconds} seconds`));
            }, timeoutSeconds * 1000);

            // Store subscription
            this.subscriptions.set(guid, { resolver: resolve, rejecter: reject, timeout });
        });
    }

    close() {
        this.connected = false;
        this.connecting = false;

        // Clear all subscriptions
        for (const [guid, subscription] of this.subscriptions) {
            clearTimeout(subscription.timeout);
            subscription.rejecter(new Error('WebSocket manager closing'));
        }
        this.subscriptions.clear();

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.close();
        }
    }
}

// Global persistent WebSocket manager instance
let persistentWS = null;

/**
 * Get or create the persistent WebSocket manager
 */
function getPersistentWebSocket() {
    if (!persistentWS) {
        persistentWS = new PersistentWebSocketManager(WEBSOCKET_URL);
    }
    return persistentWS;
}

/**
 * Subscribe to a GUID on the persistent WebSocket
 */
async function subscribePersistent(guid) {
    const wsManager = getPersistentWebSocket();
    return wsManager.subscribe(guid);
}

/**
 * Wait for compilation result using persistent WebSocket connection
 */
async function waitForCompilationResultPersistent(guid, timeout = 60) {
    const wsManager = getPersistentWebSocket();
    const overallStart = Date.now();

    try {
        const result = await wsManager.waitForResult(guid, timeout);
        const totalDuration = Date.now() - overallStart;
        console.info(`Persistent WebSocket timing: result received in ${totalDuration}ms`);
        return result;
    } catch (error) {
        const totalDuration = Date.now() - overallStart;
        console.error(`Persistent WebSocket timing: failed after ${totalDuration}ms:`, error.message);
        throw error;
    }
}

module.exports = {
    WebSocketClient,
    waitForCompilationResult,
    PersistentWebSocketManager,
    getPersistentWebSocket,
    subscribePersistent,
    waitForCompilationResultPersistent
};
