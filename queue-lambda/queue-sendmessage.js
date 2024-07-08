import {ApiGatewayManagementApiClient, PostToConnectionCommand} from '@aws-sdk/client-apigatewaymanagementapi';
import {QueueConnections} from './queue-connections.js';

async function send_message(apiGwClient, connectionId, postData) {
    try {
        const postToConnectionCommand = new PostToConnectionCommand({
            ConnectionId: connectionId,
            Data: postData,
        });
        await apiGwClient.send(postToConnectionCommand);

        return true;
    } catch (e) {
        if (e.statusCode === 410) {
            QueueConnections.remove(connectionId);
            return false;
        } else {
            throw e;
        }
    }
}

async function relay_request(apiGwClient, guid, data) {
    const subscribers = await QueueConnections.subscribers(guid);
    if (subscribers.Items || subscribers.Items.length === 0) throw new Error('No listeners for ' + guid);

    let idx = 0;
    let sub = subscribers.Items[idx];

    while (!(await send_message(apiGwClient, sub.connectionId.S, data))) {
        idx++;

        if (idx >= subscribers.Items.length) {
            throw new Error('No listeners for ' + guid);
        }

        sub = subscribers.Items[idx];
    }
}

async function handle_text_message(apiGwClient, connectionId, message) {
    if (message.startsWith('subscribe: ')) {
        const subscription = message.substring(11);
        await QueueConnections.update(connectionId, subscription);
        await send_message(apiGwClient, connectionId, `subscribed to ${subscription}`);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown text message');
    }
}

async function handle_object_message(apiGwClient, connectionId, message) {
    if (message.guid) {
        await relay_request(apiGwClient, message.guid, message);
        await send_message(apiGwClient, connectionId, `relayed message about ${message.guid}`);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown object message');
    }
}

export const handler = async event => {
    const apiGwClient = new ApiGatewayManagementApiClient({
        apiVersion: '2018-11-29',
        endpoint: `https://${event.requestContext.domainName}/${event.requestContext.stage}`,
    });

    try {
        if (typeof event.body === 'string' && event.body.startsWith('subscribe: ')) {
            await handle_text_message(apiGwClient, event.requestContext.connectionId, event.body);
        } else {
            await handle_object_message(apiGwClient, event.requestContext.connectionId, JSON.parse(event.body));
        }
    } catch (e) {
        return {statusCode: 501, body: e.message};
    }

    return {statusCode: 200, body: 'Data sent.'};
};
