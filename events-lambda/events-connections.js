import {
    DeleteItemCommand,
    DynamoDBClient,
    PutItemCommand,
    QueryCommand,
    ScanCommand,
    UpdateItemCommand,
} from '@aws-sdk/client-dynamodb';
import {config} from './config.js';

// Optimized DynamoDB client configuration for better performance
const ddbClient = new DynamoDBClient({
    region: config.region,
    maxAttempts: 2,
    requestHandler: {
        connectionTimeout: 1000,
        socketTimeout: 2000,
    },
});

export class EventsConnections {
    static async subscribers(subscription) {
        // Try GSI query with timeout, fallback to scan if GSI is cold/slow
        const queryStart = Date.now();

        try {
            // GSI query with shorter timeout to detect cold starts
            const queryCommand = new QueryCommand({
                TableName: config.connections_table,
                IndexName: 'SubscriptionIndex',
                KeyConditionExpression: '#subscription = :subscription',
                ProjectionExpression: 'connectionId',
                ExpressionAttributeNames: {
                    '#subscription': 'subscription',
                },
                ExpressionAttributeValues: {
                    ':subscription': {
                        S: subscription,
                    },
                },
            });

            // Use AbortController for proper request cancellation
            const abortController = new AbortController();
            const timeoutId = setTimeout(() => {
                abortController.abort();
            }, 200); // 200ms timeout

            const result = await ddbClient.send(queryCommand, {
                abortSignal: abortController.signal
            });

            clearTimeout(timeoutId);

            const queryTime = Date.now() - queryStart;
            // eslint-disable-next-line no-console
            console.info(`DynamoDB GSI query for ${subscription} took ${queryTime}ms, found ${result.Count} items`);
            return result;
        } catch (error) {
            const failTime = Date.now() - queryStart;

            if (error.name === 'AbortError') {
                // eslint-disable-next-line no-console
                console.warn(`GSI query aborted after ${failTime}ms (timeout), falling back to table scan`);
            } else {
                // eslint-disable-next-line no-console
                console.warn(`GSI query failed after ${failTime}ms:`, error.message, '- falling back to table scan');
            }

            // Fallback to table scan (original approach)
            const scanStart = Date.now();
            const scanCommand = new ScanCommand({
                TableName: config.connections_table,
                ProjectionExpression: 'connectionId',
                FilterExpression: '#subscription=:subscription',
                ExpressionAttributeNames: {
                    '#subscription': 'subscription',
                },
                ExpressionAttributeValues: {
                    ':subscription': {
                        S: subscription,
                    },
                },
            });
            const scanResult = await ddbClient.send(scanCommand);
            const scanTime = Date.now() - scanStart;
            // eslint-disable-next-line no-console
            console.info(`Fallback table scan for ${subscription} took ${scanTime}ms, found ${scanResult.Count} items`);
            return scanResult;
        }
    }

    static async update(id, subscription) {
        const updateCommand = new UpdateItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: id}},
            UpdateExpression: 'set #subscription = :subscription',
            ExpressionAttributeNames: {'#subscription': 'subscription'},
            ExpressionAttributeValues: {
                ':subscription': {
                    S: subscription,
                },
            },
            ReturnValues: 'ALL_NEW',
        });
        return await ddbClient.send(updateCommand);
    }

    static async unsubscribe(id, subscription) {
        // Only unsubscribe if the connection is currently subscribed to this specific subscription
        const updateCommand = new UpdateItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: id}},
            UpdateExpression: 'remove #subscription',
            ExpressionAttributeNames: {'#subscription': 'subscription'},
            ConditionExpression: '#subscription = :subscription',
            ExpressionAttributeValues: {
                ':subscription': {
                    S: subscription,
                },
            },
            ReturnValues: 'ALL_NEW',
        });
        return await ddbClient.send(updateCommand);
    }

    static async add(id) {
        const putCommand = new PutItemCommand({
            TableName: config.connections_table,
            Item: {
                connectionId: {
                    S: id,
                },
            },
        });
        await ddbClient.send(putCommand);
    }

    static async remove(id) {
        const deleteCommand = new DeleteItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: id}},
        });
        await ddbClient.send(deleteCommand);
    }
}
