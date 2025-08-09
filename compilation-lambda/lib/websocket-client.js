const WebSocket = require('ws');

// Environment variables
const WEBSOCKET_URL = process.env.WEBSOCKET_URL || '';

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
        return new Promise((resolve, reject) => {
            if (!this.url) {
                reject(new Error('WEBSOCKET_URL not configured'));
                return;
            }

            this.ws = new WebSocket(this.url, [], WS_OPTIONS);

            this.ws.on('message', (data) => {
                const messageText = data.toString();

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
                            console.info(`WebSocket unsubscribe sending for GUID: ${messageGuid}`);
                            this.ws.send(`unsubscribe: ${messageGuid}`);
                        }
                    }
                } catch (error) {
                    console.warn('Failed to parse WebSocket message:', messageText.substring(0, 100), '...', error.message);
                }
            });

            this.ws.on('error', (error) => {
                console.error(`Persistent WebSocket error:`, error);
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
                console.warn(`Persistent WebSocket closed`);
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
                console.info(`Persistent WebSocket connection established`);
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

        // Send subscribe command without waiting for acknowledgment
        console.info(`WebSocket subscription start for GUID: ${guid}`);
        this.ws.send(`subscribe: ${guid}`);
        console.info(`WebSocket subscription sent for GUID: ${guid}`);
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

    try {
        const result = await wsManager.waitForResult(guid, timeout);
        return result;
    } catch (error) {
        throw error;
    }
}

module.exports = {
    PersistentWebSocketManager,
    getPersistentWebSocket,
    subscribePersistent,
    waitForCompilationResultPersistent
};
