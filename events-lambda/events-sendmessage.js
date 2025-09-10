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

async function handle_ack_message(apiGwClient, connectionId, guid) {
    // eslint-disable-next-line no-console
    console.info(`Processing ack for GUID: ${guid} from connection ${connectionId}`);

    const senderConnectionId = await EventsConnections.getGuidSender(guid);

    if (!senderConnectionId) {
        // eslint-disable-next-line no-console
        console.warn(`No sender found for GUID: ${guid} - TODO: handle missing sender`);
        // TODO: Add logic to handle missing/disconnected senders
        // For now, just log the issue for future consideration
        return;
    }

    // eslint-disable-next-line no-console
    console.info(`Relaying ack for GUID: ${guid} to sender ${senderConnectionId}`);

    const ackMessage = JSON.stringify({
        type: 'ack',
        guid: guid,
        acknowledgedBy: connectionId,
    });

    const success = await send_message(apiGwClient, senderConnectionId, ackMessage);

    if (success) {
        // eslint-disable-next-line no-console
        console.info(`Successfully sent ack for GUID: ${guid} to sender ${senderConnectionId}`);
    } else {
        // eslint-disable-next-line no-console
        console.warn(`Failed to send ack for GUID: ${guid} - sender ${senderConnectionId} disconnected - TODO: handle`);
        // TODO: Add logic to handle disconnected senders
    }
}

async function handle_text_message(apiGwClient, connectionId, message) {
    if (message.startsWith('subscribe: ')) {
        const subscription = message.substring(11);
        // eslint-disable-next-line no-console
        console.info(`Processing subscription for ${subscription} on connection ${connectionId}`);

        try {
            await EventsConnections.update(connectionId, subscription);
            // eslint-disable-next-line no-console
            console.info(`Successfully subscribed ${connectionId} to ${subscription}`);
        } catch (error) {
            // eslint-disable-next-line no-console
            console.error(`Failed to subscribe ${connectionId} to ${subscription}:`, error);
            throw error;
        }
    } else if (message.startsWith('unsubscribe: ')) {
        const subscription = message.substring(13); // Currently unused, kept for future use
        await EventsConnections.unsubscribe(connectionId, subscription);
    } else if (message.startsWith('ack: ')) {
        const guid = message.substring(5);
        await handle_ack_message(apiGwClient, connectionId, guid);
    } else {
        await send_message(apiGwClient, connectionId, 'unknown text message');
    }
}

async function handle_object_message(apiGwClient, connectionId, message, rawMessage) {
    if (message.guid) {
        // Track the sender of this GUID for potential acks
        await EventsConnections.trackGuidSender(message.guid, connectionId);

        await relay_request(apiGwClient, message.guid, message, rawMessage);
    } else {
        // eslint-disable-next-line no-console
        console.warn('Received object message without guid:', rawMessage);
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
