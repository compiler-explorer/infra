"""Tests for compiler routing functionality."""

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from lib.compiler_routing import (
    CompilerRoutingError,
    batch_delete_items,
    batch_write_items,
    calculate_routing_changes,
    construct_environment_url,
    create_composite_key,
    fetch_discovery_compilers,
    generate_queue_name,
    generate_routing_info,
    get_current_routing_table,
    get_environment_routing_strategy,
    get_routing_table_stats,
    lookup_compiler_queue,
    lookup_compiler_routing,
    parse_composite_key,
    update_compiler_routing_table,
)


class TestCompilerRouting(unittest.TestCase):
    """Tests for compiler routing module."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_discovery_data = {
            "compilers": [
                {
                    "id": "gcc-trunk",
                    "name": "GCC trunk",
                    "exe": "/usr/bin/gcc",
                },
                {
                    "id": "clang-trunk", 
                    "name": "Clang trunk",
                    "exe": "/usr/bin/clang",
                    "remote": {
                        "target": "gpu-server",
                        "path": "/opt/compiler-explorer"
                    }
                },
                {
                    "id": "nvcc-12",
                    "name": "NVCC 12.0",
                    "exe": "/usr/local/cuda/bin/nvcc",
                    "remote": {
                        "target": "gpu-cluster",
                        "path": "/opt/nvidia"
                    }
                }
            ]
        }
        
        self.sample_routing_table = {
            "gcc-trunk": {
                "queueName": "prod-compilation-queue",
                "environment": "prod",
                "lastUpdated": "2025-01-01T00:00:00",
                "routingType": "queue",
                "targetUrl": "",
            },
            "old-compiler": {
                "queueName": "prod-compilation-queue", 
                "environment": "prod",
                "lastUpdated": "2024-12-01T00:00:00",
                "routingType": "queue",
                "targetUrl": "",
            }
        }

    @patch("lib.compiler_routing.requests")
    def test_fetch_discovery_compilers_success(self, mock_requests):
        """Test successful compiler API fetching."""
        # Mock requests response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "gcc-trunk",
                "exe": "/usr/bin/gcc",
            },
            {
                "id": "clang-trunk",
                "exe": "/usr/bin/clang",
            },
            {
                "id": "nvcc-12",
                "exe": "/usr/local/cuda/bin/nvcc",
            },
            {
                "id": "skip-this",
                "exe": "/dev/null",
            }
        ]
        mock_requests.get.return_value = mock_response
        
        result = fetch_discovery_compilers("prod")
        
        expected = {
            "gcc-trunk": {
                "id": "gcc-trunk",
                "exe": "/usr/bin/gcc",
            },
            "clang-trunk": {
                "id": "clang-trunk",
                "exe": "/usr/bin/clang",
            },
            "nvcc-12": {
                "id": "nvcc-12",
                "exe": "/usr/local/cuda/bin/nvcc",
            }
            # skip-this should be filtered out due to /dev/null exe
        }
        
        self.assertEqual(result, expected)
        mock_requests.get.assert_called_once_with(
            "https://godbolt.org/api/compilers?fields=id,exe",
            headers={"Accept": "application/json"},
            timeout=30
        )

    @patch("lib.compiler_routing.requests")
    def test_fetch_discovery_compilers_not_found(self, mock_requests):
        """Test API not found."""
        from requests.exceptions import HTTPError
        mock_requests.get.side_effect = HTTPError("404 Not Found")
        mock_requests.exceptions.RequestException = Exception
        mock_requests.exceptions.HTTPError = HTTPError
        
        with self.assertRaises(CompilerRoutingError) as context:
            fetch_discovery_compilers("staging")
        
        self.assertIn("Failed to fetch compiler API", str(context.exception))

    @patch("lib.compiler_routing.requests")
    def test_fetch_discovery_compilers_invalid_json(self, mock_requests):
        """Test invalid JSON in API response."""
        mock_response = MagicMock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_requests.get.return_value = mock_response
        mock_requests.exceptions.RequestException = Exception
        
        with self.assertRaises(CompilerRoutingError) as context:
            fetch_discovery_compilers("staging")
        
        self.assertIn("Failed to parse compiler API JSON", str(context.exception))

    @patch("lib.compiler_routing.requests")
    def test_fetch_discovery_compilers_staging_url(self, mock_requests):
        """Test correct URL construction for staging environment."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_requests.get.return_value = mock_response
        
        fetch_discovery_compilers("staging")
        
        mock_requests.get.assert_called_once_with(
            "https://godbolt.org/staging/api/compilers?fields=id,exe",
            headers={"Accept": "application/json"},
            timeout=30
        )

    @patch("lib.compiler_routing.requests")
    def test_fetch_discovery_compilers_filters_dev_null(self, mock_requests):
        """Test that compilers with /dev/null exe paths are filtered out."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "valid-compiler",
                "exe": "/usr/bin/gcc",
            },
            {
                "id": "invalid-compiler-1",
                "exe": "/dev/null",
            },
            {
                "id": "invalid-compiler-2", 
                "exe": "/path/to/dev/null/something",
            },
            {
                "id": "another-valid",
                "exe": "/opt/compiler",
            }
        ]
        mock_requests.get.return_value = mock_response
        
        result = fetch_discovery_compilers("prod")
        
        # Should only include compilers without /dev/null in exe path
        expected = {
            "valid-compiler": {
                "id": "valid-compiler",
                "exe": "/usr/bin/gcc",
            },
            "another-valid": {
                "id": "another-valid",
                "exe": "/opt/compiler",
            }
        }
        
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 2)  # Only 2 compilers should remain

    def test_generate_queue_name_local_compiler(self):
        """Test queue name generation for local compilers."""
        compiler_data = {"id": "gcc-trunk", "exe": "/usr/bin/gcc"}
        
        # Test production environment
        result = generate_queue_name(compiler_data, "prod")
        self.assertEqual(result, "prod-compilation-queue")
        
        # Test staging environment
        result = generate_queue_name(compiler_data, "staging")
        self.assertEqual(result, "staging-compilation-queue")

    def test_generate_queue_name_remote_compiler(self):
        """Test queue name generation for remote compilers."""
        compiler_data = {
            "id": "nvcc-12",
            "exe": "/usr/local/cuda/bin/nvcc",
            "remote": {"target": "gpu-cluster"}
        }
        
        # Test production environment
        result = generate_queue_name(compiler_data, "prod")
        self.assertEqual(result, "gpu-compilation-queue")
        
        # Test staging environment  
        result = generate_queue_name(compiler_data, "staging")
        self.assertEqual(result, "staging-gpu-compilation-queue")

    @patch("lib.compiler_routing.dynamodb_client")
    def test_get_current_routing_table_success(self, mock_dynamodb_client):
        """Test successful routing table retrieval."""
        # Mock paginator response
        mock_paginator = MagicMock()
        mock_page_iterator = [
            {
                "Items": [
                    {
                        "compilerId": {"S": "gcc-trunk"},
                        "queueName": {"S": "prod-compilation-queue"},
                        "environment": {"S": "prod"},
                        "lastUpdated": {"S": "2025-01-01T00:00:00"},
                        "routingType": {"S": "queue"},
                        "targetUrl": {"S": ""},
                    },
                    {
                        "compilerId": {"S": "nvcc-12"},
                        "queueName": {"S": "gpu-compilation-queue"},
                        "environment": {"S": "prod"},
                        "lastUpdated": {"S": "2025-01-01T00:00:00"},
                        "routingType": {"S": "queue"},
                        "targetUrl": {"S": ""},
                    }
                ]
            }
        ]
        mock_paginator.paginate.return_value = mock_page_iterator
        mock_dynamodb_client.get_paginator.return_value = mock_paginator
        
        result = get_current_routing_table()
        
        expected = {
            "gcc-trunk": {
                "queueName": "prod-compilation-queue",
                "environment": "prod", 
                "lastUpdated": "2025-01-01T00:00:00",
                "routingType": "queue",
                "targetUrl": "",
                "compositeKey": "gcc-trunk",
            },
            "nvcc-12": {
                "queueName": "gpu-compilation-queue",
                "environment": "prod",
                "lastUpdated": "2025-01-01T00:00:00",
                "routingType": "queue",
                "targetUrl": "",
                "compositeKey": "nvcc-12",
            }
        }
        
        self.assertEqual(result, expected)

    def test_calculate_routing_changes(self):
        """Test calculation of routing changes."""
        current_compilers = {
            "gcc-trunk": {"id": "gcc-trunk", "exe": "/usr/bin/gcc"},
            "clang-trunk": {"id": "clang-trunk", "exe": "/usr/bin/clang"},
            "nvcc-12": {
                "id": "nvcc-12", 
                "exe": "/usr/local/cuda/bin/nvcc",
                "remote": {"target": "gpu"}
            }
        }
        
        existing_table = {
            "gcc-trunk": {
                "queueName": "prod-compilation-queue",
                "environment": "prod",
                "routingType": "queue",
                "targetUrl": "",
                "compositeKey": "prod#gcc-trunk",
            },
            "old-compiler": {
                "queueName": "prod-compilation-queue",
                "environment": "prod", 
                "routingType": "queue",
                "targetUrl": "",
                "compositeKey": "prod#old-compiler",
            }
        }
        
        items_to_add, items_to_delete, items_to_update = calculate_routing_changes(
            current_compilers, existing_table, "prod"
        )
        
        # Should add clang-trunk and nvcc-12
        self.assertEqual(len(items_to_add), 2)
        self.assertIn("clang-trunk", items_to_add)
        self.assertIn("nvcc-12", items_to_add)
        
        # Should delete old-compiler (composite key format)
        self.assertEqual(items_to_delete, {"prod#old-compiler"})
        
        # Should not update gcc-trunk (unchanged)
        self.assertEqual(len(items_to_update), 0)

    @patch("lib.compiler_routing.dynamodb_client")
    def test_batch_write_items_success(self, mock_dynamodb_client):
        """Test successful batch write operation."""
        items_to_write = {
            "gcc-trunk": {
                "compilerId": "prod#gcc-trunk",
                "queueName": "prod-compilation-queue", 
                "environment": "prod",
                "lastUpdated": "2025-01-01T00:00:00",
                "routingType": "queue",
                "targetUrl": "",
            }
        }
        
        mock_dynamodb_client.batch_write_item.return_value = {"UnprocessedItems": {}}
        
        batch_write_items(items_to_write)
        
        # Verify the call was made with correct format
        mock_dynamodb_client.batch_write_item.assert_called_once()
        call_args = mock_dynamodb_client.batch_write_item.call_args[1]
        self.assertIn("RequestItems", call_args)
        self.assertIn("CompilerRouting", call_args["RequestItems"])

    @patch("lib.compiler_routing.dynamodb_client")
    def test_batch_delete_items_success(self, mock_dynamodb_client):
        """Test successful batch delete operation."""
        items_to_delete = {"old-compiler-1", "old-compiler-2"}
        
        mock_dynamodb_client.batch_write_item.return_value = {"UnprocessedItems": {}}
        
        batch_delete_items(items_to_delete)
        
        # Verify the call was made
        mock_dynamodb_client.batch_write_item.assert_called_once()
        call_args = mock_dynamodb_client.batch_write_item.call_args[1]
        self.assertIn("RequestItems", call_args)
        self.assertIn("CompilerRouting", call_args["RequestItems"])

    @patch("lib.compiler_routing.dynamodb_client")
    def test_lookup_compiler_queue_found(self, mock_dynamodb_client):
        """Test successful compiler queue lookup."""
        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "compilerId": {"S": "gcc-trunk"},
                "queueName": {"S": "prod-compilation-queue"}
            }
        }
        
        result = lookup_compiler_queue("gcc-trunk")
        self.assertEqual(result, "prod-compilation-queue")

    @patch("lib.compiler_routing.dynamodb_client")
    def test_lookup_compiler_queue_not_found(self, mock_dynamodb_client):
        """Test compiler queue lookup when not found."""
        mock_dynamodb_client.get_item.return_value = {}
        
        result = lookup_compiler_queue("nonexistent-compiler")
        self.assertIsNone(result)

    @patch("lib.compiler_routing.get_current_routing_table")
    def test_get_routing_table_stats(self, mock_get_table):
        """Test routing table statistics calculation."""
        mock_get_table.return_value = {
            "gcc-trunk": {
                "environment": "prod",
                "queueName": "prod-compilation-queue", 
                "routingType": "queue",
            },
            "clang-trunk": {
                "environment": "staging",
                "queueName": "staging-compilation-queue",
                "routingType": "queue",
            },
            "nvcc-12": {
                "environment": "prod", 
                "queueName": "gpu-compilation-queue",
                "routingType": "queue",
            }
        }
        
        result = get_routing_table_stats()
        
        self.assertEqual(result["total_compilers"], 3)
        self.assertEqual(result["environment_count"], 2)
        self.assertIn("prod", result["environments"])
        self.assertIn("staging", result["environments"])
        self.assertEqual(result["queue_distribution"]["prod-compilation-queue"], 1)
        self.assertEqual(result["queue_distribution"]["staging-compilation-queue"], 1)
        self.assertEqual(result["queue_distribution"]["gpu-compilation-queue"], 1)
        self.assertEqual(result["routing_types"]["queue"], 3)

    def test_get_environment_routing_strategy(self):
        """Test environment routing strategy lookup."""
        # Test configured environments
        self.assertEqual(get_environment_routing_strategy("prod"), "queue")
        self.assertEqual(get_environment_routing_strategy("winprod"), "url")
        self.assertEqual(get_environment_routing_strategy("staging"), "queue")
        
        # Test unknown environment defaults to queue
        self.assertEqual(get_environment_routing_strategy("unknown"), "queue")

    def test_construct_environment_url(self):
        """Test environment URL construction."""
        # Test production environment
        url = construct_environment_url("gcc-trunk", "prod", False)
        self.assertEqual(url, "https://godbolt.org/api/compiler/gcc-trunk/compile")
        
        # Test cmake endpoint
        url = construct_environment_url("gcc-trunk", "prod", True)
        self.assertEqual(url, "https://godbolt.org/api/compiler/gcc-trunk/cmake")
        
        # Test non-production environment
        url = construct_environment_url("gcc-trunk", "staging", False)
        self.assertEqual(url, "https://godbolt.org/staging/api/compiler/gcc-trunk/compile")

    def test_generate_routing_info_queue(self):
        """Test routing info generation for queue routing."""
        compiler_data = {"id": "gcc-trunk", "exe": "/usr/bin/gcc"}
        
        # Test queue routing environment
        result = generate_routing_info(compiler_data, "prod")
        expected = {
            "queueName": "prod-compilation-queue",
            "routingType": "queue",
            "targetUrl": "",
        }
        self.assertEqual(result, expected)

    def test_generate_routing_info_url(self):
        """Test routing info generation for URL routing."""
        compiler_data = {"id": "gcc-trunk", "exe": "/usr/bin/gcc"}
        
        # Test URL routing environment
        result = generate_routing_info(compiler_data, "winprod")
        expected = {
            "queueName": "",
            "routingType": "url",
            "targetUrl": "https://godbolt.org/winprod/api/compiler/gcc-trunk/compile",
        }
        self.assertEqual(result, expected)

    @patch("lib.compiler_routing.dynamodb_client")
    def test_lookup_compiler_routing_found(self, mock_dynamodb_client):
        """Test successful compiler routing lookup."""
        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "compilerId": {"S": "prod#gcc-trunk"},
                "queueName": {"S": "prod-compilation-queue"},
                "environment": {"S": "prod"},
                "routingType": {"S": "queue"},
                "targetUrl": {"S": ""},
            }
        }
        
        result = lookup_compiler_routing("gcc-trunk", "prod")
        expected = {
            "queueName": "prod-compilation-queue",
            "environment": "prod",
            "routingType": "queue",
            "targetUrl": "",
        }
        self.assertEqual(result, expected)

    @patch("lib.compiler_routing.dynamodb_client")
    def test_lookup_compiler_routing_url_type(self, mock_dynamodb_client):
        """Test compiler routing lookup for URL routing."""
        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "compilerId": {"S": "winprod#msvc-19"},
                "queueName": {"S": ""},
                "environment": {"S": "winprod"},
                "routingType": {"S": "url"},
                "targetUrl": {"S": "https://godbolt.org/winprod/api/compiler/msvc-19/compile"},
            }
        }
        
        result = lookup_compiler_routing("msvc-19", "winprod")
        expected = {
            "queueName": "",
            "environment": "winprod",
            "routingType": "url",
            "targetUrl": "https://godbolt.org/winprod/api/compiler/msvc-19/compile",
        }
        self.assertEqual(result, expected)

    @patch("lib.compiler_routing.dynamodb_client")
    def test_lookup_compiler_routing_not_found(self, mock_dynamodb_client):
        """Test compiler routing lookup when not found."""
        # Mock both composite key and fallback attempts to return empty
        mock_dynamodb_client.get_item.return_value = {}
        
        result = lookup_compiler_routing("nonexistent-compiler", "prod")
        self.assertIsNone(result)

    @patch("lib.compiler_routing.fetch_discovery_compilers")
    @patch("lib.compiler_routing.get_current_routing_table")
    @patch("lib.compiler_routing.batch_write_items")
    @patch("lib.compiler_routing.batch_delete_items")
    def test_update_compiler_routing_table_success(
        self, mock_batch_delete, mock_batch_write, mock_get_table, mock_fetch_discovery
    ):
        """Test successful routing table update."""
        mock_fetch_discovery.return_value = {"gcc-trunk": {"id": "gcc-trunk"}}
        mock_get_table.return_value = {"old-compiler": {"environment": "prod"}}
        
        result = update_compiler_routing_table("prod")
        
        # Should call batch operations
        mock_batch_write.assert_called_once()
        mock_batch_delete.assert_called_once() 
        
        # Should return change counts
        self.assertIn("added", result)
        self.assertIn("updated", result)
        self.assertIn("deleted", result)

    @patch("lib.compiler_routing.fetch_discovery_compilers")
    @patch("lib.compiler_routing.get_current_routing_table")
    @patch("lib.compiler_routing.batch_write_items")
    @patch("lib.compiler_routing.batch_delete_items")
    def test_update_compiler_routing_table_dry_run(
        self, mock_batch_delete, mock_batch_write, mock_get_table, mock_fetch_discovery
    ):
        """Test dry-run mode for routing table update."""
        mock_fetch_discovery.return_value = {"gcc-trunk": {"id": "gcc-trunk"}} 
        mock_get_table.return_value = {"old-compiler": {"environment": "prod"}}
        
        result = update_compiler_routing_table("prod", dry_run=True)
        
        # Should not call batch operations in dry-run mode
        mock_batch_write.assert_not_called()
        mock_batch_delete.assert_not_called()
        
        # Should still return change counts
        self.assertIn("added", result)
        self.assertIn("updated", result)
        self.assertIn("deleted", result)


if __name__ == "__main__":
    unittest.main()