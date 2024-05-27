# Lambdas for execution/build-queue websocket mechanism

Note these are 3 different lambda's in 1 directory

How it works:

- `queue-onconnect.js` is triggered first, the connection is added to a DynamoDB table.
- `queue-ondisconnect.js` is triggered when there's a disconnect, the connection is deleted from the DynamoDB table.
- `queue-sendmessage.js` when someone sends a message to the websocket, other connections can be looked up in the
  DynamoDB table and be sent messages to.
