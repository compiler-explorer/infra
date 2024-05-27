import {QueueConnections} from './queue-connections.js';

export const handler = async event => {
    // console.log('event', JSON.stringify(event, null, 2));

    try {
        QueueConnections.add(event.requestContext.connectionId);
    } catch (err) {
        return {statusCode: 500, body: 'Failed to connect: ' + JSON.stringify(err)};
    }

    return {statusCode: 200, body: 'Connected.'};
};
