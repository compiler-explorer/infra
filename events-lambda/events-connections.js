import {DeleteItemCommand, DynamoDBClient, PutItemCommand, QueryCommand, ScanCommand} from '@aws-sdk/client-dynamodb';
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

// Simple in-memory cache: Set<"connectionId:subscription">
const subscriptionCache = new Set();

export class EventsConnections {
    static async subscribers(subscription) {
        // Check cache first - find all connectionIds with this subscription
        const cachedConnections = [];
        for (const entry of subscriptionCache) {
            if (entry.endsWith(`:${subscription}`)) {
                const connectionId = entry.split(':')[0];
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
                // Extract actual connection ID from composite key (connectionId#subscription)
                const actualConnectionId = item.connectionId.S.split('#')[0];
                subscriptionCache.add(`${actualConnectionId}:${subscription}`);
            }
        }

        // Merge cached connections with DynamoDB results to handle GSI eventual consistency
        // Use a Set to avoid duplicates
        const connectionIdSet = new Set();

        // Add DynamoDB results
        if (result.Items) {
            for (const item of result.Items) {
                // Extract actual connection ID from composite key (connectionId#subscription)
                const actualConnectionId = item.connectionId.S.split('#')[0];
                connectionIdSet.add(actualConnectionId);
            }
        }

        // Add cached results to handle GSI propagation delay
        for (const conn of cachedConnections) {
            connectionIdSet.add(conn.connectionId.S);
        }

        // Convert Set back to the expected format
        const mergedItems = Array.from(connectionIdSet).map(id => ({connectionId: {S: id}}));

        // eslint-disable-next-line no-console
        if (cachedConnections.length > 0 || result.Count > 0) {
            // eslint-disable-next-line no-console
            console.info(
                `Cache: ${cachedConnections.length} items, DynamoDB: ${result.Count || 0} items, ` +
                    `Merged: ${mergedItems.length} items for ${subscription}`,
            );
        }

        // Return a result object with merged items
        return {
            Items: mergedItems,
            Count: mergedItems.length,
            ScannedCount: result.ScannedCount || 0,
        };
    }

    static async update(id, subscription) {
        // Update cache first for instant response
        subscriptionCache.add(`${id}:${subscription}`);

        // Use PutItem with composite key to support multiple subscriptions per connection
        // Each connection-subscription pair is stored as a separate item
        const putCommand = new PutItemCommand({
            TableName: config.connections_table,
            Item: {
                connectionId: {S: `${id}#${subscription}`},
                subscription: {S: subscription},
            },
        });

        try {
            await ddbClient.send(putCommand);
            return {Attributes: {connectionId: {S: id}, subscription: {S: subscription}}};
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`Failed to update subscription in DynamoDB for ${id}:`, error);
            // Remove from cache on DynamoDB failure to maintain consistency
            subscriptionCache.delete(`${id}:${subscription}`);
            throw error;
        }
    }

    static async unsubscribe(id, subscription) {
        // Remove from cache first for instant response
        subscriptionCache.delete(`${id}:${subscription}`);

        // Delete the specific connection-subscription item from DynamoDB
        const deleteCommand = new DeleteItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: `${id}#${subscription}`}},
            // No condition expression - we don't care if the item exists
            // This prevents ConditionalCheckFailedException when multiple unsubscribe
            // requests are processed or item was already removed
        });

        try {
            await ddbClient.send(deleteCommand);
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`Failed to unsubscribe ${id} from ${subscription} in DynamoDB:`, error);
            // Don't re-add to cache - prioritize fast response over consistency
        }

        // Return response indicating successful unsubscription
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
        // Remove all entries for this connection from cache first
        for (const entry of subscriptionCache) {
            if (entry.startsWith(`${id}:`)) {
                subscriptionCache.delete(entry);
            }
        }

        // Find and delete all connection-subscription items from DynamoDB
        // Use scan with begins_with filter to find all composite keys for this connection
        const scanCommand = new ScanCommand({
            TableName: config.connections_table,
            FilterExpression: 'begins_with(connectionId, :connectionPrefix)',
            ExpressionAttributeValues: {
                ':connectionPrefix': {S: `${id}#`},
            },
            ProjectionExpression: 'connectionId',
        });

        try {
            const scanResult = await ddbClient.send(scanCommand);

            // Delete all found items
            if (scanResult.Items && scanResult.Items.length > 0) {
                const deletePromises = scanResult.Items.map(item => {
                    const deleteCommand = new DeleteItemCommand({
                        TableName: config.connections_table,
                        Key: {connectionId: {S: item.connectionId.S}},
                    });
                    return ddbClient.send(deleteCommand);
                });

                await Promise.all(deletePromises);
            }
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`Failed to remove connection ${id} items from DynamoDB:`, error);
        }
    }
}
