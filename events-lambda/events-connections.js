import {
    DeleteItemCommand,
    DynamoDBClient,
    PutItemCommand,
    QueryCommand,
    UpdateItemCommand,
} from '@aws-sdk/client-dynamodb';
import {config} from './config.js';

// Optimized DynamoDB client configuration for production performance
const ddbClient = new DynamoDBClient({
    region: config.region,
    maxAttempts: 3, // Increased retries for better reliability
    requestHandler: {
        connectionTimeout: 500, // Faster connection setup
        socketTimeout: 1500, // Reduced socket timeout for faster failures
        connectionPoolSize: 10, // Pool connections for better performance
    },
    // Enable keep-alive for connection reuse
    httpOptions: {
        keepAlive: true,
        keepAliveMsecs: 30000, // 30 seconds keep-alive
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

        // Always query DynamoDB to ensure cross-container consistency
        // Cache is used as optimization but not relied upon for correctness
        // eslint-disable-next-line no-console
        console.info(`DynamoDB query start for subscription: ${subscription}`);
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
        // eslint-disable-next-line no-console
        console.info(`DynamoDB query end for subscription: ${subscription}, found ${result.Count} items`);

        // Update cache with results from DynamoDB
        if (result.Items) {
            for (const item of result.Items) {
                subscriptionCache.set(item.connectionId.S, subscription);
            }
        }

        // eslint-disable-next-line no-console
        if (cachedConnections.length > 0) {
            // eslint-disable-next-line no-console
            console.info(`Cache had ${cachedConnections.length} items for ${subscription}`);
        } else {
            // eslint-disable-next-line no-console
            console.info(`Cache miss for ${subscription}`);
        }

        return result;
    }

    static async update(id, subscription) {
        // Update cache first for instant response
        subscriptionCache.set(id, subscription);

        // Update DynamoDB synchronously to ensure cross-container consistency
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

        try {
            return await ddbClient.send(updateCommand);
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`Failed to update subscription in DynamoDB for ${id}:`, error);
            // Remove from cache on DynamoDB failure to maintain consistency
            subscriptionCache.delete(id);
            throw error;
        }
    }

    static async unsubscribe(id) {
        // Remove from cache first for instant response
        subscriptionCache.delete(id);

        // Update DynamoDB asynchronously - don't await
        const updateCommand = new UpdateItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: id}},
            UpdateExpression: 'remove #subscription',
            ExpressionAttributeNames: {'#subscription': 'subscription'},
            // No condition expression - we don't care if the subscription matches or exists
            // We just want to ensure it's removed. This prevents ConditionalCheckFailedException
            // when multiple unsubscribe requests are processed or subscription was already removed
            ReturnValues: 'ALL_NEW',
        });

        // Fire and forget - don't await DynamoDB update
        ddbClient.send(updateCommand).catch(error => {
            // Only log if it's not an attribute not found error (which is expected)
            if (error.name !== 'ValidationException' || !error.message?.includes('provided attribute')) {
                // eslint-disable-next-line no-console
                console.error(`Failed to unsubscribe ${id} from DynamoDB:`, error);
            }
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
