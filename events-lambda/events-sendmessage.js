import {ApiGatewayManagementApiClient, PostToConnectionCommand} from '@aws-sdk/client-apigatewaymanagementapi';
import {EventsConnections} from './events-connections.js';

async function send_message(apiGwClient, connectionId, postData) {
    try {
        const postToConnectionCommand = new PostToConnectionCommand({
            ConnectionId: connectionId,
            Data: postData,
        });
        await apiGwClient.send(postToConnectionCommand);

        return true;
    } catch (e) {
        // eslint-disable-next-line no-console
        console.error(e);

        if (e.statusCode === 410) {
            await EventsConnections.remove(connectionId);
            return false;
        } else {
            throw e;
        }
    }
}

async function relay_request(apiGwClient, guid, data) {
    const subscribers = await EventsConnections.subscribers(guid);
    if (subscribers.Count === 0) throw new Error('No listeners for ' + guid);

    for (let idx = 0; idx < subscribers.Count; idx++) {
        const sub = subscribers.Items[idx];

        await send_message(apiGwClient, sub.connectionId.S, JSON.stringify(data));
    }
}

async function handle_text_message(apiGwClient, connectionId, message) {
    if (message.startsWith('subscribe: ')) {
        const subscription = message.substring(11);
        await EventsConnections.update(connectionId, subscription);
    } else if (message.startsWith('unsubscribe: ')) {
        const subscription = message.substring(13);
        await EventsConnections.unsubscribe(connectionId, subscription);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown text message');
    }
}

async function handle_object_message(apiGwClient, connectionId, message) {
    if (message.guid) {
        await relay_request(apiGwClient, message.guid, message);
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
        if (typeof event.body === 'string' && !event.body.startsWith('{')) {
            await handle_text_message(apiGwClient, event.requestContext.connectionId, event.body);
        } else {
            await handle_object_message(apiGwClient, event.requestContext.connectionId, JSON.parse(event.body));
        }
    } catch (e) {
        // eslint-disable-next-line no-console
        console.error(e);
        return {statusCode: 501, body: e.message};
    }

    return {statusCode: 200, body: 'Data sent.'};
};
