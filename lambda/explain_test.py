import json
import unittest
from unittest.mock import MagicMock, patch

import explain


class TestExplainLambda(unittest.TestCase):
    def setUp(self):
        # Create a minimal event
        self.event = {
            "httpMethod": "POST",
            "body": json.dumps(
                {
                    "language": "c++",
                    "compiler": "g++",
                    "code": "int square(int x) {\n  return x * x;\n}",
                    "compilationOptions": ["-O2", "-g"],
                    "instructionSet": "amd64",
                    "asm": [
                        {"text": "square(int):", "source": None, "labels": []},
                        {
                            "text": "        mov     eax, edi",
                            "source": {"file": None, "line": 1, "column": 21},
                            "labels": [],
                        },
                        {
                            "text": "        imul    eax, edi",
                            "source": {"file": None, "line": 2, "column": 10},
                            "labels": [],
                        },
                        {"text": "        ret", "source": {"file": None, "line": 2, "column": 10}, "labels": []},
                    ],
                    "labelDefinitions": {"square(int)": 0},
                }
            ),
        }

    @patch("explain.get_anthropic_client")
    def test_lambda_handler_success(self, mock_get_anthropic):
        # Set up the mock
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "This assembly code implements a simple square function..."
        mock_message.content = [mock_content]
        # Add usage information to the mock
        mock_message.usage = MagicMock()
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_message
        mock_get_anthropic.return_value = mock_client

        # Call the lambda_handler
        response = explain.lambda_handler(self.event, None)

        # Verify response
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("application/json", response["headers"]["Content-Type"])

        # Parse the body
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "success")
        self.assertIn("explanation", body)
        self.assertEqual(body["explanation"], "This assembly code implements a simple square function...")

        # Check new fields
        self.assertIn("model", body)
        self.assertEqual(body["model"], explain.MODEL)

        # Check usage information
        self.assertIn("usage", body)
        self.assertEqual(body["usage"]["input_tokens"], 100)
        self.assertEqual(body["usage"]["output_tokens"], 50)
        self.assertEqual(body["usage"]["total_tokens"], 150)

        # Check cost information
        self.assertIn("cost", body)
        self.assertIsInstance(body["cost"]["input_cost"], float)
        self.assertIsInstance(body["cost"]["output_cost"], float)
        self.assertIsInstance(body["cost"]["total_cost"], float)

        # Verify the mock was called correctly
        mock_client.messages.create.assert_called_once()
        args, kwargs = mock_client.messages.create.call_args

        # Check that key parameters were passed
        self.assertEqual(kwargs["model"], explain.MODEL)
        self.assertEqual(kwargs["max_tokens"], explain.MAX_TOKENS)
        self.assertIn("system", kwargs)

        # Verify the system prompt contains appropriate instructions
        system_prompt = kwargs["system"]
        self.assertIn("expert", system_prompt.lower())
        self.assertIn("assembly", system_prompt.lower())
        self.assertIn("c++", system_prompt.lower())
        self.assertIn("amd64", system_prompt.lower())

        # Check that the messages array contains user and assistant messages
        messages = kwargs["messages"]
        self.assertEqual(len(messages), 2)
        # Check user message
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(len(messages[0]["content"]), 2)
        self.assertEqual(messages[0]["content"][0]["type"], "text")
        self.assertIn("amd64", messages[0]["content"][0]["text"])
        self.assertEqual(messages[0]["content"][1]["type"], "text")
        # Check assistant message
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(len(messages[1]["content"]), 1)
        self.assertEqual(messages[1]["content"][0]["type"], "text")
        self.assertIn("analysis", messages[1]["content"][0]["text"])

        # Check the structured data has expected fields
        structured_data = json.loads(messages[0]["content"][1]["text"])
        self.assertEqual(structured_data["language"], "c++")
        self.assertEqual(structured_data["compiler"], "g++")
        self.assertEqual(structured_data["sourceCode"], "int square(int x) {\n  return x * x;\n}")

    @patch("explain.get_anthropic_client")
    def test_lambda_handler_options(self, mock_get_anthropic):
        # Set up an OPTIONS event
        options_event = {
            "httpMethod": "OPTIONS",
        }

        # Call the lambda_handler
        response = explain.lambda_handler(options_event, None)

        # Verify CORS headers
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("Access-Control-Allow-Origin", response["headers"])

        # Verify the mock was not called
        mock_get_anthropic.assert_not_called()

    def test_validate_input_success(self):
        """Test input validation with valid input"""
        # Valid input
        input_body = {
            "language": "c++",
            "compiler": "g++",
            "code": "int main() { return 0; }",
            "asm": [{"text": "main:", "source": None}],
        }
        valid, message = explain.validate_input(input_body)
        self.assertTrue(valid)
        self.assertEqual(message, "")

    def test_validate_input_missing_field(self):
        """Test input validation with missing fields"""
        # Missing language
        input_body = {"compiler": "g++", "code": "int main() { return 0; }", "asm": [{"text": "main:", "source": None}]}
        valid, message = explain.validate_input(input_body)
        self.assertFalse(valid)
        self.assertIn("Missing required field", message)

    def test_validate_input_code_too_long(self):
        """Test input validation with code too long"""
        # Code too long
        input_body = {
            "language": "c++",
            "compiler": "g++",
            "code": "x" * (explain.MAX_CODE_LENGTH + 1),
            "asm": [{"text": "main:", "source": None}],
        }
        valid, message = explain.validate_input(input_body)
        self.assertFalse(valid)
        self.assertIn("exceeds maximum length", message)

    def test_validate_input_invalid_asm(self):
        """Test input validation with invalid assembly format"""
        # Assembly not an array
        input_body = {"language": "c++", "compiler": "g++", "code": "int main() { return 0; }", "asm": "main:"}
        valid, message = explain.validate_input(input_body)
        self.assertFalse(valid)
        self.assertIn("Assembly must be an array", message)

    def test_validate_input_empty_asm(self):
        """Test input validation with empty assembly array"""
        # Empty assembly array
        input_body = {"language": "c++", "compiler": "g++", "code": "int main() { return 0; }", "asm": []}
        valid, message = explain.validate_input(input_body)
        self.assertFalse(valid)
        self.assertIn("Assembly array cannot be empty", message)

    def test_select_important_assembly(self):
        """Test the assembly line selection functionality"""
        # Create test assembly with more lines than the max
        test_asm = []
        for i in range(500):
            asm_line = {"text": f"instruction {i}", "source": None, "labels": []}
            # Add source mapping to some lines to make them important
            if i % 20 == 0:
                asm_line["source"] = {"line": i // 20, "column": 0}
            # Add some return instructions
            if i % 100 == 99:
                asm_line["text"] = "ret"
            test_asm.append(asm_line)

        # Label definitions for function starts
        label_defs = {"func1": 0, "func2": 100, "func3": 200, "func4": 300, "func5": 400}

        # Run the function
        result = explain.select_important_assembly(test_asm, label_defs)

        # Verify the result has fewer lines than the original but less than the max
        self.assertLess(len(result), len(test_asm))
        self.assertLessEqual(len(result), explain.MAX_ASSEMBLY_LINES)

        # Check that we have some omission markers
        has_markers = any("isOmissionMarker" in line for line in result)
        self.assertTrue(has_markers)

        # Check that important lines (with sources) are included
        has_source_lines = False
        for line in result:
            if "isOmissionMarker" not in line and line.get("source") is not None:
                if isinstance(line["source"], dict) and line["source"].get("line") is not None:
                    has_source_lines = True
                    break
        self.assertTrue(has_source_lines)

    def test_prepare_structured_data(self):
        """Test structured data preparation"""
        # Basic body
        body = {
            "language": "c++",
            "compiler": "g++",
            "code": "int square(int x) { return x * x; }",
            "compilationOptions": ["-O2"],
            "instructionSet": "amd64",
            "asm": [
                {"text": "square:", "source": None},
                {"text": "  imul eax, edi", "source": {"line": 1, "column": 10}},
            ],
            "labelDefinitions": {"square": 0},
            "stderr": ["warning: unused variable"],
            "optimizationOutput": ["loop vectorized"],
        }

        # Call the function
        result = explain.prepare_structured_data(body)

        # Verify all required fields exist
        self.assertEqual(result["language"], "c++")
        self.assertEqual(result["compiler"], "g++")
        self.assertEqual(result["sourceCode"], "int square(int x) { return x * x; }")
        self.assertEqual(result["compilationOptions"], ["-O2"])
        self.assertEqual(result["instructionSet"], "amd64")
        self.assertEqual(len(result["assembly"]), 2)
        self.assertEqual(result["labelDefinitions"], {"square": 0})
        self.assertEqual(result["compilerMessages"], ["warning: unused variable"])
        self.assertEqual(result["optimizationRemarks"], ["loop vectorized"])
        self.assertEqual(result["truncated"], False)

    def test_prepare_structured_data_truncation(self):
        """Test structured data preparation with truncation for large assembly"""
        # Create a large assembly array
        large_asm = []
        for i in range(explain.MAX_ASSEMBLY_LINES + 100):
            large_asm.append({"text": f"instruction {i}", "source": None})

        body = {
            "language": "c++",
            "compiler": "g++",
            "code": "int main() { return 0; }",
            "compilationOptions": ["-O2"],
            "asm": large_asm,
        }

        # Call the function
        result = explain.prepare_structured_data(body)

        # Verify truncation occurred
        self.assertEqual(result["truncated"], True)
        self.assertEqual(result["originalLength"], explain.MAX_ASSEMBLY_LINES + 100)
        self.assertLessEqual(len(result["assembly"]), explain.MAX_ASSEMBLY_LINES)

    def test_lambda_handler_json_error(self):
        """Test lambda handler with invalid JSON"""
        # Set up an event with invalid JSON
        invalid_event = {"httpMethod": "POST", "body": "{invalid json"}

        # Call the lambda_handler
        response = explain.lambda_handler(invalid_event, None)

        # Verify response indicates error
        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "error")
        self.assertIn("Invalid JSON", body["message"])


if __name__ == "__main__":
    unittest.main()
