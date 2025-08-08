import {
    DeleteItemCommand,
    DynamoDBClient,
    PutItemCommand,
    QueryCommand,
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

// Simple in-memory cache: connectionId -> subscription
const subscriptionCache = new Map();

export class EventsConnections {
    static async subscribers(subscription) {
        // Check cache first - find all connectionIds with this subscription
        const cachedConnections = [];
        for (const [connectionId, cachedSubscription] of subscriptionCache) {
            if (cachedSubscription === subscription) {
                cachedConnections.push({connectionId: {S: connectionId}});
            }
        }

        if (cachedConnections.length > 0) {
            // eslint-disable-next-line no-console
            console.info(`Cache hit for ${subscription}, found ${cachedConnections.length} items`);
            return {
                Items: cachedConnections,
                Count: cachedConnections.length,
            };
        }

        // Cache miss - query DynamoDB GSI
        const queryStart = Date.now();
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

        const result = await ddbClient.send(queryCommand);
        const queryTime = Date.now() - queryStart;

        // Update cache with results
        if (result.Items) {
            for (const item of result.Items) {
                subscriptionCache.set(item.connectionId.S, subscription);
            }
        }

        // eslint-disable-next-line no-console
        console.info(
            `GSI query for ${subscription} took ${queryTime}ms, found ${result.Count} items, ` +
            `cached ${result.Count} entries`,
        );
        return result;
    }

    static async update(id, subscription) {
        // Update cache first for instant response
        subscriptionCache.set(id, subscription);

        // Update DynamoDB asynchronously - don't await
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

        // Fire and forget - don't await DynamoDB update
        ddbClient.send(updateCommand).catch(error => {
            // eslint-disable-next-line no-console
            console.error(`Failed to update subscription in DynamoDB for ${id}:`, error);
            // Don't remove from cache - prioritize fast response over consistency
        });

        // Return immediately - cache is already updated
        return {Attributes: {connectionId: {S: id}, subscription: {S: subscription}}};
    }

    static async unsubscribe(id, subscription) {
        // Remove from cache first for instant response
        subscriptionCache.delete(id);

        // Update DynamoDB asynchronously - don't await
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

        // Fire and forget - don't await DynamoDB update
        ddbClient.send(updateCommand).catch(error => {
            // eslint-disable-next-line no-console
            console.error(`Failed to unsubscribe ${id} from DynamoDB:`, error);
            // Don't re-add to cache - prioritize fast response over consistency
        });

        // Return immediately - cache is already updated
        return {Attributes: {connectionId: {S: id}}};
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

        // Remove from cache
        subscriptionCache.delete(id);
    }
}
