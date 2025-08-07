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
        const connectStart = Date.now();
        return new Promise((resolve, reject) => {
            if (!this.url) {
                reject(new Error('WEBSOCKET_URL environment variable not set'));
                return;
            }

            this.ws = new WebSocket(this.url);

            this.ws.on('open', () => {
                const connectDuration = Date.now() - connectStart;
                console.info(`WebSocket timing: connection established in ${connectDuration}ms`);
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
                        const totalTime = Date.now() - connectStart;
                        console.info(`WebSocket timing: received result for ${this.guid} after ${totalTime}ms`);
                        // The entire message IS the result
                        this.result = message;
                        this.ws.close();
                    }
                } catch (error) {
                    console.warn(`Received invalid JSON message: ${data.toString().substring(0, 100)}... Error:`, error);
                }
            });

            this.ws.on('error', (error) => {
                const errorTime = Date.now() - connectStart;
                console.error(`WebSocket error for ${this.guid} after ${errorTime}ms:`, error);
                this.error = error;
                reject(error);
            });

            this.ws.on('close', () => {
                this.connected = false;
            });

            // Connection timeout
            setTimeout(() => {
                if (!this.connected) {
                    const timeoutDuration = Date.now() - connectStart;
                    console.warn(`WebSocket connection timeout after ${timeoutDuration}ms`);
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
                console.info(`WebSocket timing: retrying in 1000ms...`);
                await new Promise(resolve => setTimeout(resolve, 1000)); // Brief delay before retry
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
