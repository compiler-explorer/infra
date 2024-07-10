import {QueueConnections} from './queue-connections.js';

export const handler = async event => {
    try {
        await QueueConnections.add(event.requestContext.connectionId);
    } catch (err) {
        return {statusCode: 500, body: 'Failed to connect: ' + JSON.stringify(err)};
    }

    return {statusCode: 200, body: 'Connected.'};
};
