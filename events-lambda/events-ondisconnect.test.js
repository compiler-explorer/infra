import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DynamoDBClient} from '@aws-sdk/client-dynamodb';
import {handler} from './events-ondisconnect.js';

test('removes the connection and returns 200', async t => {
    const calls = [];
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        calls.push(cmd);
        return {Items: []};
    });
    const res = await handler({requestContext: {connectionId: 'conn-bye'}});
    assert.equal(res.statusCode, 200);
    assert.ok(calls.length > 0);
});

test('still returns 200 when dynamo errors (removal failures are swallowed)', async t => {
    t.mock.method(DynamoDBClient.prototype, 'send', async () => {
        throw new Error('boom');
    });
    const res = await handler({requestContext: {connectionId: 'conn-bye-err'}});
    assert.equal(res.statusCode, 200);
});
