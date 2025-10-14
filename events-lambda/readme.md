# Lambdas for execution/build-queue websocket mechanism

Note these are 3 different lambda's in 1 directory

How it works:

- `events-onconnect.js` is triggered first, the connection is added to a DynamoDB table.
- `events-ondisconnect.js` is triggered when there's a disconnect, the connection is deleted from the DynamoDB table.
- `events-sendmessage.js` when someone sends a message to the websocket, other connections can be looked up in the
  DynamoDB table and be sent messages to.

## Multiple Subscriptions Support

Each connection can now subscribe to multiple GUIDs simultaneously:

- Subscriptions are stored as separate DynamoDB items using composite keys
- Cache uses composite key format: `connectionId:subscription`
- Partial unsubscription is supported (remove individual subscriptions while keeping others)

## Scenario

Client A is a x86 compilation instance Client B is a aarch64 execution instance

- Client A has pushed a request for execution
- Client A connects to websocket
- Client A says: "subscribe: 1234abc"
- Client A says: "subscribe: 5678def" (multiple subscriptions supported)
- Client B connects to websocket
- Client B says: {"guid": "1234abc", "code": "42"}
- Client A receives: {"guid": "1234abc", "code": "42"}
- Client A handles the message
- Client A says: "unsubscribe: 1234abc" (removes only this subscription)
- Client A remains subscribed to: "5678def"

## Tables

`events-connections`

- `connectionId` S (Primary Key) - Format: `actualConnectionId#subscription` (composite key)
- `subscription` S (GSI) - The subscription GUID for efficient lookups

### Examples:
```
{connectionId: "conn123#guid456", subscription: "guid456"}
{connectionId: "conn123#guid789", subscription: "guid789"}
```

Each connection-subscription pair is stored as a separate item, enabling multiple subscriptions per connection while maintaining efficient GSI queries.
