import {ApiGatewayManagementApiClient, PostToConnectionCommand} from '@aws-sdk/client-apigatewaymanagementapi';
import {QueueConnections} from './queue-connections.js';

async function send_message(apiGwClient, id, postData) {
    try {
        const postToConnectionCommand = new PostToConnectionCommand({
            ConnectionId: id,
            Data: postData,
        });
        await apiGwClient.send(postToConnectionCommand);

        return true;
    } catch (e) {
        if (e.statusCode === 410) {
            QueueConnections.remove(id);
            return false;
        } else {
            throw e;
        }
    }
}

async function relay_request(arch, request) {
    const subscribers = await QueueConnections.subscribers(arch);
    if (subscribers.Items || subscribers.Items.length === 0) throw new Error('No listeners for ' + arch);

    let idx = 0;
    let sub = subscribers.Items[idx];

    while (!send_message(sub.connectionId.S, request)) {
        idx++;

        if (idx >= subscribers.Items.length) {
            throw new Error('No listeners for ' + arch);
        }

        sub = subscribers.Items[idx];
    }
}

async function handle_text_message(id, message) {
    if (typeof message === 'string' && message.startsWith('subscribe: ')) {
        await QueueConnections.update(id, message.substring(11));
    } else if (typeof message === 'object' && message.arch) {
        await relay_request(message.arch, message);
    } else {
        // console.error('Someone said something unknown: ' + message);
    }
}

export const handler = async event => {
    const apiGwClient = new ApiGatewayManagementApiClient({
        apiVersion: '2018-11-29',
        endpoint: `https://${event.requestContext.domainName}/${event.requestContext.stage}`,
    });

    const postData = JSON.parse(event.body).data;

    try {
        handle_text_message(apiGwClient, event.requestContext.connectionId, postData);
    } catch (e) {
        return {statusCode: 501, body: e.message};
    }

    return {statusCode: 200, body: 'Data sent.'};
};
