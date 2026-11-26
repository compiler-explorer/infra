import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DeleteItemCommand, DynamoDBClient, PutItemCommand, QueryCommand, ScanCommand} from '@aws-sdk/client-dynamodb';
import {EventsConnections} from './events-connections.js';

// Intercept the module-level DynamoDB client's send() and record every command.
// `responder` returns the canned response for a given command.
function recordSend(t, responder = () => ({})) {
    const calls = [];
    t.mock.method(DynamoDBClient.prototype, 'send', async cmd => {
        calls.push(cmd);
        return responder(cmd);
    });
    return calls;
}

test('add stores the connection id with a ttl', async t => {
    const calls = recordSend(t);
    await EventsConnections.add('conn-add');
    assert.equal(calls.length, 1);
    assert.ok(calls[0] instanceof PutItemCommand);
    assert.equal(calls[0].input.Item.connectionId.S, 'conn-add');
    assert.ok(Number(calls[0].input.Item.ttl.N) > 0);
});

test('update writes a composite-key item for the subscription', async t => {
    const calls = recordSend(t);
    await EventsConnections.update('conn-up', 'guid-up');
    assert.ok(calls[0] instanceof PutItemCommand);
    assert.equal(calls[0].input.Item.connectionId.S, 'conn-up#guid-up');
    assert.equal(calls[0].input.Item.subscription.S, 'guid-up');
});

test('update gives the subscription a ttl so it cannot leak', async t => {
    const calls = recordSend(t);
    const before = Math.floor(Date.now() / 1000);
    await EventsConnections.update('conn-ttl', 'guid-ttl');
    const ttl = Number(calls[0].input.Item.ttl.N);
    // Comfortably past the router's 60s deadline, so it can never expire a subscription still being waited on.
    assert.ok(ttl >= before + 300, `ttl ${ttl} should be at least 300s ahead of ${before}`);
    assert.ok(ttl <= Math.floor(Date.now() / 1000) + 300);
});

test('unsubscribe deletes the composite-key item', async t => {
    const calls = recordSend(t);
    await EventsConnections.unsubscribe('conn-un', 'guid-un');
    assert.ok(calls[0] instanceof DeleteItemCommand);
    assert.equal(calls[0].input.Key.connectionId.S, 'conn-un#guid-un');
});

test('subscribers returns the underlying connection ids from a dynamo query', async t => {
    recordSend(t, cmd => {
        if (cmd instanceof QueryCommand) {
            return {Items: [{connectionId: {S: 'subbed#guid-q'}}], Count: 1, ScannedCount: 1};
        }
        return {};
    });
    const result = await EventsConnections.subscribers('guid-q');
    assert.equal(result.Count, 1);
    assert.equal(result.Items[0].connectionId.S, 'subbed');
});

test('remove scans for the connection prefix and deletes every match', async t => {
    const calls = recordSend(t, cmd => {
        if (cmd instanceof ScanCommand) {
            return {Items: [{connectionId: {S: 'conn-rm#a'}}, {connectionId: {S: 'conn-rm#b'}}]};
        }
        return {};
    });
    await EventsConnections.remove('conn-rm');
    const scan = calls.find(c => c instanceof ScanCommand);
    assert.ok(scan);
    assert.equal(scan.input.ExpressionAttributeValues[':connectionPrefix'].S, 'conn-rm#');
    assert.equal(calls.filter(c => c instanceof DeleteItemCommand).length, 2);
});

test('getGuidSender returns the tracked sender from cache without querying', async t => {
    const calls = recordSend(t);
    await EventsConnections.trackGuidSender('guid-track', 'sender-conn');
    const sender = await EventsConnections.getGuidSender('guid-track');
    assert.equal(sender, 'sender-conn');
    assert.equal(calls.filter(c => c instanceof QueryCommand).length, 0);
});

test('getGuidSender falls back to dynamo when not cached', async t => {
    recordSend(t, cmd => {
        if (cmd instanceof QueryCommand) {
            return {Items: [{senderConnectionId: {S: 'fallback-sender'}}]};
        }
        return {};
    });
    const sender = await EventsConnections.getGuidSender('guid-uncached');
    assert.equal(sender, 'fallback-sender');
});

test('subscribers retries the index when a subscription has not propagated yet', async t => {
    // SubscriptionIndex is a GSI, so a write that has already succeeded can be invisible to a
    // query moments later. Seen when a compile finishes faster than the index propagates.
    let attempts = 0;
    const calls = recordSend(t, cmd => {
        if (!(cmd instanceof QueryCommand)) return {};
        attempts++;
        return attempts < 2 ? {Items: [], Count: 0} : {Items: [{connectionId: {S: 'conn-late'}}], Count: 1};
    });

    const result = await EventsConnections.subscribers('guid-late');

    assert.equal(result.Count, 1);
    assert.equal(result.Items[0].connectionId.S, 'conn-late');
    assert.ok(calls.length >= 2, 'should have queried more than once');
});

test('subscribers does not retry when the first query finds someone', async t => {
    let attempts = 0;
    recordSend(t, cmd => {
        if (!(cmd instanceof QueryCommand)) return {};
        attempts++;
        return {Items: [{connectionId: {S: 'conn-fast'}}], Count: 1};
    });

    const result = await EventsConnections.subscribers('guid-fast');

    assert.equal(result.Count, 1);
    assert.equal(attempts, 1, 'the common path must not pay for the retry');
});

test('subscribers gives up after its retries and reports nobody', async t => {
    let attempts = 0;
    recordSend(t, cmd => {
        if (!(cmd instanceof QueryCommand)) return {};
        attempts++;
        return {Items: [], Count: 0};
    });

    const result = await EventsConnections.subscribers('guid-absent');

    assert.equal(result.Count, 0);
    assert.equal(attempts, 3, 'one initial query plus the two retries');
});

test('subscribers still waits on the index even when the cache has someone', async t => {
    // The cache is an optimisation and may be incomplete or stale, so it does not excuse us
    // from letting the index propagate - it might name a different or additional subscriber.
    let attempts = 0;
    recordSend(t, cmd => {
        if (!(cmd instanceof QueryCommand)) return {};
        attempts++;
        return {Items: [], Count: 0};
    });
    await EventsConnections.update('conn-cached', 'guid-cached');
    attempts = 0;

    const result = await EventsConnections.subscribers('guid-cached');

    assert.equal(result.Count, 1, 'the cached subscriber is still returned');
    assert.equal(result.Items[0].connectionId.S, 'conn-cached');
    assert.equal(attempts, 3, 'and the index was given its chances regardless');
});
