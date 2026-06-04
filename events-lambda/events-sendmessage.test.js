import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DynamoDBClient, QueryCommand} from '@aws-sdk/client-dynamodb';
import {ApiGatewayManagementApiClient, PostToConnectionCommand} from '@aws-sdk/client-apigatewaymanagementapi';
import {handler} from './events-sendmessage.js';

const baseContext = {domainName: 'example.com', stage: 'prod', connectionId: 'sender-conn'};

function event(body) {
    return {requestContext: baseContext, body};
}

test('a subscribe message stores the subscription and returns 200', async t => {
    const calls = [];
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        calls.push(cmd);
        return {};
    });
    const res = await handler(event('subscribe: guid-sub'));
    assert.equal(res.statusCode, 200);
    assert.ok(calls.some(c => c.input?.Item?.connectionId?.S === 'sender-conn#guid-sub'));
});

test('an object message relays to subscribers and returns 200', async t => {
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        if (cmd instanceof QueryCommand) {
            return {Items: [{connectionId: {S: 'listener-conn#guid-relay'}}], Count: 1};
        }
        return {};
    });
    const posted = [];
    t.mock.method(ApiGatewayManagementApiClient.prototype, 'send', async cmd => {
        posted.push(cmd);
        return {};
    });
    const res = await handler(event(JSON.stringify({guid: 'guid-relay', code: '42'})));
    assert.equal(res.statusCode, 200);
    assert.equal(posted.length, 1);
    assert.ok(posted[0] instanceof PostToConnectionCommand);
    assert.equal(posted[0].input.ConnectionId, 'listener-conn');
});

test('an object message with no subscribers returns 501', async t => {
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        if (cmd instanceof QueryCommand) {
            return {Items: [], Count: 0};
        }
        return {};
    });
    t.mock.method(ApiGatewayManagementApiClient.prototype, 'send', async () => ({}));
    const res = await handler(event(JSON.stringify({guid: 'guid-empty', code: '42'})));
    assert.equal(res.statusCode, 501);
});

test('an unknown text message is echoed back to the sender', async t => {
    const posted = [];
    t.mock.method(DynamoDBClient.prototype, 'send', async () => ({}));
    t.mock.method(ApiGatewayManagementApiClient.prototype, 'send', async cmd => {
        posted.push(cmd);
        return {};
    });
    const res = await handler(event('hello there'));
    assert.equal(res.statusCode, 200);
    assert.equal(posted.length, 1);
    assert.equal(posted[0].input.ConnectionId, 'sender-conn');
    assert.equal(posted[0].input.Data, 'unknown text message');
});
