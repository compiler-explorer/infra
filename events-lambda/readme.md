# Lambdas for execution/build-queue websocket mechanism

Note these are 3 different lambda's in 1 directory

How it works:

- `events-onconnect.js` is triggered first, the connection is added to a DynamoDB table.
- `events-ondisconnect.js` is triggered when there's a disconnect, the connection is deleted from the DynamoDB table.
- `events-sendmessage.js` when someone sends a message to the websocket, other connections can be looked up in the
  DynamoDB table and be sent messages to.

## Scenario

Client A is a x86 compilation instance Client B is a aarch64 execution instance

- Client A has pushed a request for execution
- Client A connects to websocket
- Client A says: "subscribe: 1234abc"
- Client B connects to websocket
- Client B says: {"guid": "1234abc", "code": "42"}
- Client A receives: {"guid": "1234abc", "code": "42"}
- Client A handles the message

## Tables

`queue-connections`

- `connectionId` S
- `subscription` S
