import {EventsConnections} from './events-connections.js';

export const handler = async event => {
    try {
        await EventsConnections.add(event.requestContext.connectionId);
    } catch (err) {
        return {statusCode: 500, body: 'Failed to connect: ' + JSON.stringify(err)};
    }

    return {statusCode: 200, body: 'Connected.'};
};
