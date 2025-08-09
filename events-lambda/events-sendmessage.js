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

async function relay_request(apiGwClient, guid, data, rawData = null) {
    // eslint-disable-next-line no-console
    console.info(`Subscriber lookup start for GUID: ${guid}`);
    const subscribers = await EventsConnections.subscribers(guid);
    // eslint-disable-next-line no-console
    console.info(`Subscriber lookup end for GUID: ${guid}, found ${subscribers.Count} subscribers`);

    if (subscribers.Count === 0) throw new Error('No listeners for ' + guid);

    // eslint-disable-next-line no-console
    console.info(`Message relay start for GUID: ${guid} to ${subscribers.Count} subscribers`);
    // Use raw data if provided (avoids re-stringification), otherwise stringify the parsed object
    const postData = rawData || JSON.stringify(data);

    for (let idx = 0; idx < subscribers.Count; idx++) {
        const sub = subscribers.Items[idx];

        await send_message(apiGwClient, sub.connectionId.S, postData);
    }
    // eslint-disable-next-line no-console
    console.info(`Message relay end for GUID: ${guid}`);
}

async function handle_text_message(apiGwClient, connectionId, message) {
    if (message.startsWith('subscribe: ')) {
        const subscription = message.substring(11);
        // eslint-disable-next-line no-console
        console.info(`Processing subscription for ${subscription} on connection ${connectionId}`);

        await EventsConnections.update(connectionId, subscription);
    } else if (message.startsWith('unsubscribe: ')) {
        const subscription = message.substring(13);
        await EventsConnections.unsubscribe(connectionId, subscription);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown text message');
    }
}

async function handle_object_message(apiGwClient, connectionId, message, rawMessage) {
    if (message.guid) {
        await relay_request(apiGwClient, message.guid, message, rawMessage);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown object message');
    }
}

// Cache API Gateway client across Lambda invocations for better performance
let cachedApiGwClient = null;
let cachedEndpoint = null;

export const handler = async event => {
    const currentEndpoint = `https://${event.requestContext.domainName}/${event.requestContext.stage}`;

    // Reuse client if same endpoint, create new one if endpoint changes
    if (!cachedApiGwClient || cachedEndpoint !== currentEndpoint) {
        cachedApiGwClient = new ApiGatewayManagementApiClient({
            apiVersion: '2018-11-29',
            endpoint: currentEndpoint,
        });
        cachedEndpoint = currentEndpoint;
    }

    const apiGwClient = cachedApiGwClient;

    try {
        if (typeof event.body === 'string' && !event.body.startsWith('{')) {
            await handle_text_message(apiGwClient, event.requestContext.connectionId, event.body);
        } else {
            // Parse once to get the guid, but pass the raw string to avoid re-stringification
            const parsedBody = JSON.parse(event.body);
            await handle_object_message(apiGwClient, event.requestContext.connectionId, parsedBody, event.body);
        }
    } catch (e) {
        // eslint-disable-next-line no-console
        console.error(e);
        return {statusCode: 501, body: e.message};
    }

    return {statusCode: 200, body: 'Data sent.'};
};
