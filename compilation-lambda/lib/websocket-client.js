const WebSocket = require('ws');

// Environment variables
const WEBSOCKET_URL = process.env.WEBSOCKET_URL || '';
const RETRY_COUNT = parseInt(process.env.RETRY_COUNT || '1', 10);

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
    }

    connect() {
        return new Promise((resolve, reject) => {
            if (!this.url) {
                reject(new Error('WEBSOCKET_URL environment variable not set'));
                return;
            }

            this.ws = new WebSocket(this.url);

            this.ws.on('open', () => {
                this.connected = true;
                // Subscribe to messages for this GUID
                const subscribeMsg = `subscribe: ${this.guid}`;
                this.ws.send(subscribeMsg);
                resolve();
            });

            this.ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());
                    const messageGuid = message.guid;

                    if (messageGuid === this.guid) {
                        // The entire message IS the result
                        this.result = message;
                        this.ws.close();
                    }
                } catch (error) {
                    console.warn(`Received invalid JSON message: ${data.toString().substring(0, 100)}... Error:`, error);
                }
            });

            this.ws.on('error', (error) => {
                console.error(`WebSocket error for ${this.guid}:`, error);
                this.error = error;
                reject(error);
            });

            this.ws.on('close', () => {
                this.connected = false;
            });

            // Connection timeout
            setTimeout(() => {
                if (!this.connected) {
                    this.ws.close();
                    reject(new Error('WebSocket connection timeout'));
                }
            }, 5000);
        });
    }

    waitForResult(timeout) {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();

            const checkResult = () => {
                if (this.result !== null) {
                    resolve(this.result);
                    return;
                }

                if (this.error) {
                    reject(this.error);
                    return;
                }

                if (Date.now() - startTime > timeout * 1000) {
                    this.ws.close();
                    reject(new Error(`No response received within ${timeout} seconds`));
                    return;
                }

                setTimeout(checkResult, 100);
            };

            checkResult();
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
    let lastError = null;

    for (let attempt = 0; attempt <= RETRY_COUNT; attempt++) {
        try {
            const client = new WebSocketClient(WEBSOCKET_URL, guid);
            await client.connect();
            const result = await client.waitForResult(timeout);
            return result;
        } catch (error) {
            lastError = error;
            if (attempt < RETRY_COUNT) {
                await new Promise(resolve => setTimeout(resolve, 1000)); // Brief delay before retry
            }
        }
    }

    throw lastError || new Error('All WebSocket attempts failed');
}

module.exports = {
    WebSocketClient,
    waitForCompilationResult
};
