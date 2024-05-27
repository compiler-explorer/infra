import {
    DeleteItemCommand,
    DynamoDBClient,
    PutItemCommand,
    ScanCommand,
    UpdateItemCommand,
} from '@aws-sdk/client-dynamodb';
import {config} from './config.js';

const ddbClient = new DynamoDBClient({region: config.region});

export class QueueConnections {
    // static async all() {
    //     const scanCommand = new ScanCommand({
    //         TableName: config.connections_table,
    //         ProjectionExpression: 'connectionId',
    //     });
    //     return await ddbClient.send(scanCommand);
    // }

    static async subscribers(subscription) {
        const scanCommand = new ScanCommand({
            TableName: config.connections_table,
            ProjectionExpression: 'connectionId',
            FilterExpression: 'subscription=' + subscription,
        });
        return await ddbClient.send(scanCommand);
    }

    static async update(id, subscription) {
        const updateCommand = new UpdateItemCommand({
            TableName: config.connections_table,
            Key: {connectionId: {S: id}},
            AttributeUpdates: {
                subscription: {
                    Value: subscription,
                    Action: 'PUT',
                },
            },
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
