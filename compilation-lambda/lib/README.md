# Compilation Lambda Library Modules

This directory contains the modular components of the compilation lambda, organized by responsibility:

## 📁 Module Structure

### `aws-clients.js`
**AWS Service Initialization**
- Configures DynamoDB, SQS, and STS clients
- Provides cached account ID lookup
- Exports AWS SDK command classes for dependency injection

### `routing.js` 
**Compiler Routing Logic**
- DynamoDB lookup for compiler-to-queue/URL routing
- Request body parsing (JSON/plain text)
- SQS message formatting and sending
- Environment-aware composite key handling

### `websocket-client.js`
**WebSocket Communication**
- WebSocket connection management for compilation results
- GUID-based message subscription
- Retry logic and error handling
- Result polling with configurable timeouts

### `http-forwarder.js`
**Direct URL Forwarding**
- HTTP request forwarding to environment URLs
- CMake/compile endpoint URL transformation
- Header filtering and content-type detection
- Error handling for network failures

### `utils.js`
**Request/Response Utilities**
- Path parsing for compiler ID extraction
- GUID generation for request tracking
- ALB-compatible response formatting
- CMake request detection

## 🔧 Architecture Benefits

### **Separation of Concerns**
Each module handles a specific responsibility, making the code easier to understand and maintain.

### **Testability**
Modules can be unit tested independently with focused mocks and assertions.

### **Reusability**
Components can be reused across different Lambda functions or environments.

### **Maintainability**
Changes to specific functionality are isolated to relevant modules.

## 📊 Dependencies

```
index.js (Main Handler)
├── routing.js
│   └── aws-clients.js
├── websocket-client.js
├── http-forwarder.js
└── utils.js
```

## 🧪 Testing

Each module is mocked independently in the test suite, allowing for focused testing of the main handler logic without complex AWS SDK mocking.