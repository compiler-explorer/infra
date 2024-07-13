import {EventsConnections} from './events-connections.js';

export const handler = async event => {
    try {
        await EventsConnections.remove(event.requestContext.connectionId);
    } catch (err) {
        return {statusCode: 500, body: 'Failed to disconnect: ' + JSON.stringify(err)};
    }

    return {statusCode: 200, body: 'Disconnected.'};
};
