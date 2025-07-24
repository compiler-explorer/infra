import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

import lambda_function


class TestCompilationLambda(unittest.TestCase):
    """Test cases for compilation Lambda function."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock environment variables
        self.env_patcher = patch.dict(
            os.environ,
            {
                "RETRY_COUNT": "2",
                "TIMEOUT_SECONDS": "30",
                "SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo",
                "WEBSOCKET_URL": "wss://events.test.com/environment",
            },
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.env_patcher.stop()

    def test_generate_guid(self):
        """Test GUID generation."""
        guid1 = lambda_function.generate_guid()
        guid2 = lambda_function.generate_guid()

        # Should be valid UUIDs
        uuid.UUID(guid1)
        uuid.UUID(guid2)

        # Should be unique
        self.assertNotEqual(guid1, guid2)

    def test_extract_compiler_id(self):
        """Test compiler ID extraction from paths."""
        test_cases = [
            # Production format: /api/compiler/{id}/compile
            ("/api/compiler/gcc12/compile", "gcc12"),
            ("/api/compiler/clang15/cmake", "clang15"),
            ("api/compiler/rust-nightly/compile", "rust-nightly"),
            ("/api/compiler/g++12.2/compile", "g++12.2"),
            ("/api/compiler/gcc12/invalid", "gcc12"),  # Still extracts valid compiler ID
            # Environment-prefixed format: /{env}/api/compiler/{id}/compile
            ("/beta/api/compiler/gcc12/compile", "gcc12"),
            ("/staging/api/compiler/clang15/cmake", "clang15"),
            ("beta/api/compiler/g++12.2/compile", "g++12.2"),
            ("/beta/api/compiler/gcc12/invalid", "gcc12"),  # Still extracts valid compiler ID
            # Invalid paths
            ("/invalid/path", None),
            ("/api/compilers/gcc12/compile", None),  # Legacy plural format no longer supported
            ("/api/compilers/", None),
            ("/api/compiler/", None),  # Missing compiler ID
            ("/beta/api/compiler/", None),  # Missing compiler ID
            ("/beta/api/compilers/gcc12/compile", None),  # Wrong plural form
            ("", None),
        ]

        for path, expected in test_cases:
            with self.subTest(path=path):
                result = lambda_function.extract_compiler_id(path)
                self.assertEqual(result, expected)

    def test_is_cmake_request(self):
        """Test cmake request detection."""
        test_cases = [
            # Production format
            ("/api/compiler/gcc12/cmake", True),
            ("/api/compiler/clang15/compile", False),
            # Environment-prefixed format
            ("/beta/api/compiler/gcc12/cmake", True),
            ("/staging/api/compiler/clang15/compile", False),
            # Invalid cases
            ("/api/compilers/gcc12/cmake", True),  # Legacy plural format still detects /cmake ending
            ("cmake", False),  # Must end with /cmake
            ("", False),
        ]

        for path, expected in test_cases:
            with self.subTest(path=path):
                result = lambda_function.is_cmake_request(path)
                self.assertEqual(result, expected)

    @patch("lambda_function.sqs")
    @patch("lambda_function.SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo")
    def test_send_to_sqs_success(self, mock_sqs):
        """Test successful SQS message sending."""
        mock_sqs.send_message.return_value = {"MessageId": "test-message-id"}

        headers = {"Content-Type": "application/json"}
        lambda_function.send_to_sqs("test-guid", "gcc12", '{"source": "test"}', False, headers)

        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args

        self.assertEqual(call_args[1]["QueueUrl"], "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo")
        self.assertEqual(call_args[1]["MessageGroupId"], "default")
        self.assertEqual(call_args[1]["MessageDeduplicationId"], "test-guid")

        # Check message body
        message_body = json.loads(call_args[1]["MessageBody"])
        self.assertEqual(message_body["guid"], "test-guid")
        self.assertEqual(message_body["compilerId"], "gcc12")
        self.assertEqual(message_body["isCMake"], False)
        self.assertEqual(message_body["source"], "test")
        self.assertEqual(message_body["options"], [])  # Default added since not in request
        # Check that required defaults are added
        self.assertEqual(message_body["backendOptions"], {})
        self.assertEqual(message_body["filters"], {})
        self.assertEqual(message_body["tools"], [])
        self.assertEqual(message_body["executeParameters"], {})
        self.assertEqual(message_body["libraries"], [])
        self.assertEqual(message_body["files"], [])
        # Optional fields not added if not in request
        self.assertNotIn("bypassCache", message_body)
        self.assertNotIn("lang", message_body)
        self.assertNotIn("allowStoreCodeDebug", message_body)

    @patch("lambda_function.sqs")
    @patch("lambda_function.SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo")
    def test_send_to_sqs_plain_text(self, mock_sqs):
        """Test SQS message sending with plain text body."""
        mock_sqs.send_message.return_value = {"MessageId": "test-message-id"}

        headers = {"Content-Type": "text/plain"}
        plain_text_source = "int main() { return 0; }"
        lambda_function.send_to_sqs("test-guid", "gcc12", plain_text_source, False, headers)

        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args

        # Check message body contains plain text as source
        message_body = json.loads(call_args[1]["MessageBody"])
        self.assertEqual(message_body["source"], plain_text_source)
        self.assertEqual(message_body["options"], [])
        self.assertEqual(message_body["headers"]["Content-Type"], "text/plain")

    @patch("lambda_function.sqs")
    @patch("lambda_function.SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo")
    def test_send_to_sqs_complete_request(self, mock_sqs):
        """Test SQS message sending with complete compilation request."""
        mock_sqs.send_message.return_value = {"MessageId": "test-message-id"}

        complete_request = {
            "source": "int main() { return 0; }",
            "options": ["-O2", "-std=c++17"],
            "backendOptions": {"produceBinaryObject": True},
            "filters": {"binary": True, "execute": False},
            "bypassCache": True,
            "tools": [{"id": "tool1", "args": ["--flag"]}],
            "executeParameters": {"args": ["arg1"], "stdin": "input"},
            "libraries": [{"id": "lib1", "version": "1.0"}],
            "files": [{"name": "file.h", "contents": "#pragma once"}],
            "lang": "c++",
            "allowStoreCodeDebug": True,
            "customField": "should be preserved",
        }

        headers = {"Content-Type": "application/json"}
        lambda_function.send_to_sqs("test-guid", "gcc12", json.dumps(complete_request), False, headers)

        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args

        # Check that all fields from the original request are preserved
        message_body = json.loads(call_args[1]["MessageBody"])
        self.assertEqual(message_body["guid"], "test-guid")
        self.assertEqual(message_body["compilerId"], "gcc12")
        self.assertEqual(message_body["isCMake"], False)

        # Check that all original request fields are preserved
        self.assertEqual(message_body["source"], "int main() { return 0; }")
        self.assertEqual(message_body["options"], ["-O2", "-std=c++17"])
        self.assertEqual(message_body["backendOptions"], {"produceBinaryObject": True})
        self.assertEqual(message_body["filters"], {"binary": True, "execute": False})
        self.assertEqual(message_body["bypassCache"], True)
        self.assertEqual(message_body["tools"], [{"id": "tool1", "args": ["--flag"]}])
        self.assertEqual(message_body["executeParameters"], {"args": ["arg1"], "stdin": "input"})
        self.assertEqual(message_body["libraries"], [{"id": "lib1", "version": "1.0"}])
        self.assertEqual(message_body["files"], [{"name": "file.h", "contents": "#pragma once"}])
        self.assertEqual(message_body["lang"], "c++")
        self.assertEqual(message_body["allowStoreCodeDebug"], True)
        self.assertEqual(message_body["customField"], "should be preserved")

    @patch("lambda_function.sqs")
    @patch("lambda_function.SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-queue.fifo")
    def test_send_to_sqs_prevents_double_encoding(self, mock_sqs):
        """Test that SQS message prevents double JSON encoding."""
        mock_sqs.send_message.return_value = {"MessageId": "test-message-id"}

        request_data = {"source": "test", "options": ["-O2"]}
        headers = {"Content-Type": "application/json"}
        lambda_function.send_to_sqs("test-guid", "gcc12", json.dumps(request_data), False, headers)

        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args

        # The message body should be a valid JSON string, not double-encoded
        message_body_str = call_args[1]["MessageBody"]
        self.assertIsInstance(message_body_str, str)

        # Should be able to parse as JSON (not indexed characters)
        message_body = json.loads(message_body_str)
        self.assertIsInstance(message_body, dict)
        self.assertEqual(message_body["source"], "test")
        self.assertEqual(message_body["options"], ["-O2"])

        # Ensure it's not double-encoded (would cause indexed characters)
        self.assertNotIn("0", message_body)  # Would exist if double-encoded
        self.assertNotIn("1", message_body)  # Would exist if double-encoded

    @patch("lambda_function.sqs")
    @patch("lambda_function.SQS_QUEUE_URL", "")
    def test_send_to_sqs_no_url(self, mock_sqs):
        """Test SQS sending when URL is not set."""
        with self.assertRaises(lambda_function.SQSError):
            lambda_function.send_to_sqs("test-guid", "gcc12", "{}", False, {})

    @patch("lambda_function.sqs")
    def test_send_to_sqs_client_error(self, mock_sqs):
        """Test SQS sending with client error."""
        from botocore.exceptions import ClientError

        mock_sqs.send_message.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterValue", "Message": "Invalid parameter"}}, "SendMessage"
        )

        with self.assertRaises(lambda_function.SQSError):
            lambda_function.send_to_sqs("test-guid", "gcc12", "{}", False, {})

    def test_create_error_response(self):
        """Test error response creation."""
        response = lambda_function.create_error_response(400, "Bad request")

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(response["headers"]["Content-Type"], "application/json")
        self.assertIn("Access-Control-Allow-Origin", response["headers"])

        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Bad request")

    def test_create_success_response_json(self):
        """Test success response creation with JSON format."""
        result = {"code": 0, "stdout": ["Hello World"]}
        response = lambda_function.create_success_response(result, "application/json")

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/json; charset=utf-8")

        body = json.loads(response["body"])
        self.assertEqual(body, result)

    def test_create_success_response_plain_text(self):
        """Test success response creation with plain text format."""
        result = {"code": 0, "asm": [{"text": "main:"}, {"text": "    xor eax, eax"}, {"text": "    ret"}]}
        response = lambda_function.create_success_response(result, "text/plain")

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response["body"], "main:\n    xor eax, eax\n    ret")

    def test_parse_request_body_json(self):
        """Test parsing JSON request body."""
        body = '{"source": "int main() {}", "options": ["-O2"]}'
        result = lambda_function.parse_request_body(body, "application/json")

        self.assertEqual(result["source"], "int main() {}")
        self.assertEqual(result["options"], ["-O2"])

    def test_parse_request_body_plain_text(self):
        """Test parsing plain text request body."""
        body = "int main() { return 0; }"
        result = lambda_function.parse_request_body(body, "text/plain")

        self.assertEqual(result, {"source": body})

    @patch("lambda_function.WebSocketClient")
    @patch("lambda_function.send_to_sqs")
    @patch("lambda_function.generate_guid")
    def test_lambda_handler_success(self, mock_generate_guid, mock_send_to_sqs, mock_ws_client_class):
        """Test successful lambda handler execution."""
        mock_generate_guid.return_value = "test-guid-123"

        # Mock WebSocket client
        mock_ws_client = Mock()
        mock_ws_client.connected = True
        mock_ws_client.wait_for_result.return_value = {"guid": "test-guid-123", "code": 0, "stdout": ["Success"]}
        mock_ws_client_class.return_value = mock_ws_client

        event = {
            "path": "/beta/api/compiler/gcc12/compile",
            "httpMethod": "POST",
            "body": '{"source": "int main() { return 0; }"}',
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        }

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        mock_generate_guid.assert_called_once()
        mock_send_to_sqs.assert_called_once_with(
            "test-guid-123",
            "gcc12",
            '{"source": "int main() { return 0; }"}',
            False,
            {"Content-Type": "application/json", "Accept": "application/json"},
        )
        mock_ws_client.wait_for_result.assert_called_once_with(60)

    @patch("lambda_function.wait_for_compilation_result")
    @patch("lambda_function.send_to_sqs")
    @patch("lambda_function.generate_guid")
    def test_lambda_handler_production_path(self, mock_generate_guid, mock_send_to_sqs, mock_wait_for_result):
        """Test successful lambda handler execution with production path format."""
        mock_generate_guid.return_value = "test-guid-456"
        mock_wait_for_result.return_value = {"code": 0, "stdout": ["Success"]}

        event = {
            "path": "/api/compiler/gcc12/compile",
            "httpMethod": "POST",
            "body": '{"source": "int main() { return 0; }"}',
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        }

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        mock_generate_guid.assert_called_once()
        mock_send_to_sqs.assert_called_once_with(
            "test-guid-456",
            "gcc12",
            '{"source": "int main() { return 0; }"}',
            False,
            {"Content-Type": "application/json", "Accept": "application/json"},
        )
        mock_wait_for_result.assert_called_once_with("test-guid-456", 60)

    def test_lambda_handler_invalid_method(self):
        """Test lambda handler with invalid HTTP method."""
        event = {"path": "/beta/api/compiler/gcc12/compile", "httpMethod": "GET", "body": ""}

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 405)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Method not allowed")

    def test_lambda_handler_invalid_path(self):
        """Test lambda handler with invalid path."""
        event = {"path": "/invalid/path", "httpMethod": "POST", "body": "{}"}

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "Invalid path: compiler ID not found")

    @patch("lambda_function.wait_for_compilation_result")
    @patch("lambda_function.send_to_sqs")
    @patch("lambda_function.generate_guid")
    def test_lambda_handler_sqs_error(self, mock_generate_guid, mock_send_to_sqs, mock_wait_for_result):
        """Test lambda handler with SQS error."""
        mock_generate_guid.return_value = "test-guid-123"
        mock_send_to_sqs.side_effect = lambda_function.SQSError("Queue not found")

        event = {"path": "/beta/api/compiler/gcc12/compile", "httpMethod": "POST", "body": "{}", "headers": {}}

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 500)
        body = json.loads(response["body"])
        self.assertIn("Failed to queue compilation request", body["error"])

    @patch("lambda_function.WebSocketClient")
    @patch("lambda_function.send_to_sqs")
    @patch("lambda_function.generate_guid")
    def test_lambda_handler_timeout(self, mock_generate_guid, mock_send_to_sqs, mock_ws_client_class):
        """Test lambda handler with WebSocket timeout."""
        mock_generate_guid.return_value = "test-guid-123"

        # Mock WebSocket client that times out
        mock_ws_client = Mock()
        mock_ws_client.connected = True
        mock_ws_client.wait_for_result.side_effect = lambda_function.WebSocketTimeoutError(
            "No response received within 30 seconds"
        )
        mock_ws_client_class.return_value = mock_ws_client

        event = {"path": "/beta/api/compiler/gcc12/compile", "httpMethod": "POST", "body": "{}", "headers": {}}

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 408)
        body = json.loads(response["body"])
        self.assertIn("Compilation timeout", body["error"])

    def test_lambda_handler_cmake_request(self):
        """Test lambda handler recognizes cmake requests."""
        with (
            patch("lambda_function.wait_for_compilation_result") as mock_wait,
            patch("lambda_function.send_to_sqs") as mock_send,
            patch("lambda_function.generate_guid") as mock_guid,
        ):
            mock_guid.return_value = "test-guid-123"
            mock_wait.return_value = {"code": 0}

            event = {"path": "/beta/api/compiler/gcc12/cmake", "httpMethod": "POST", "body": "{}", "headers": {}}

            lambda_function.lambda_handler(event, None)

            # Verify that isCMake is set to True
            mock_send.assert_called_once_with("test-guid-123", "gcc12", "{}", True, {})

    @patch("lambda_function.wait_for_compilation_result")
    @patch("lambda_function.send_to_sqs")
    @patch("lambda_function.generate_guid")
    def test_lambda_handler_plain_text_request(self, mock_generate_guid, mock_send_to_sqs, mock_wait_for_result):
        """Test lambda handler with plain text request and text/plain Accept header."""
        mock_generate_guid.return_value = "test-guid-123"
        mock_wait_for_result.return_value = {
            "code": 0,
            "asm": [{"text": "main:"}, {"text": "    xor eax, eax"}, {"text": "    ret"}],
        }

        event = {
            "path": "/beta/api/compiler/gcc12/compile",
            "httpMethod": "POST",
            "body": "int main() { return 0; }",
            "headers": {"Content-Type": "text/plain", "Accept": "text/plain"},
        }

        response = lambda_function.lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response["body"], "main:\n    xor eax, eax\n    ret")

        # Verify the request was sent with plain text body
        mock_send_to_sqs.assert_called_once()
        call_args = mock_send_to_sqs.call_args
        self.assertEqual(call_args[0][2], "int main() { return 0; }")


class TestWebSocketClient(unittest.TestCase):
    """Test cases for WebSocket client."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = lambda_function.WebSocketClient("wss://test.com/ws", "test-guid")

    def test_websocket_client_init(self):
        """Test WebSocket client initialization."""
        self.assertEqual(self.client.url, "wss://test.com/ws")
        self.assertEqual(self.client.guid, "test-guid")
        self.assertIsNone(self.client.result)
        self.assertFalse(self.client.connected)

    def test_on_message_correct_guid(self):
        """Test WebSocket message handling with correct GUID."""
        mock_ws = Mock()
        message_data = {"guid": "test-guid", "code": 0, "stdout": ["Success"], "stderr": []}
        message = json.dumps(message_data)

        self.client.on_message(mock_ws, message)

        self.assertEqual(self.client.result, message_data)
        mock_ws.close.assert_called_once()

    def test_on_message_wrong_guid(self):
        """Test WebSocket message handling with wrong GUID."""
        mock_ws = Mock()
        message = json.dumps({"guid": "different-guid", "result": {"code": 0, "stdout": ["Success"]}})

        self.client.on_message(mock_ws, message)

        self.assertIsNone(self.client.result)
        mock_ws.close.assert_not_called()

    def test_on_message_invalid_json(self):
        """Test WebSocket message handling with invalid JSON."""
        mock_ws = Mock()

        # Should not raise exception
        self.client.on_message(mock_ws, "invalid json")

        self.assertIsNone(self.client.result)
        mock_ws.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
