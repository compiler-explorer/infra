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
        // Use table scan for consistent performance (~300ms)
        // GSI has unpredictable cold start issues (800ms+) that timeout doesn't reliably prevent
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

        const result = await ddbClient.send(scanCommand);
        const scanTime = Date.now() - scanStart;
        // eslint-disable-next-line no-console
        console.info(`Table scan for ${subscription} took ${scanTime}ms, found ${result.Count} items`);
        return result;
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
