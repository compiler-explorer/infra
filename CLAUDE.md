# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test/Lint Commands

- Setup environment: `make ce`
- Run all tests: `make test`
- Run a single test: `uv run pytest bin/test/path_to_test.py::TestClass::test_method -v`
- Run static checks: `make static-checks`
- Check code style/linting: `make pre-commit`
- Install pre-commit hooks: `make install-pre-commit`
- Build lambda package: `make lambda-package`
- Build events lambda package: `make events-lambda-package`

## Important Workflow Requirements

- ALWAYS run pre-commit hooks before committing: `make pre-commit`
- The hooks will run tests and lint checks, and will fail the commit if there are any issues
- Failing to run pre-commit hooks may result in style issues and commit failures
- For comprehensive validation, run `make static-checks` before committing (includes all linting and type checking)
- If static checks fail, fix the issues before committing to avoid CI failures
- **Critical**: After fixing any issues, run `make static-checks` AGAIN. Repeat until it passes completely. Only commit when `make static-checks` runs with zero errors.

### Correct Commit Workflow
1. Make changes
2. Run `make static-checks`
3. If it fails, fix the issues
4. Run `make static-checks` again (fixes might introduce new issues or be auto-formatted)
5. Repeat steps 3-4 until `make static-checks` passes completely
6. Only then create the commit

## Code Style Guidelines

- Python formatting: Black with 120 char line length
- Use type hints for Python code (mypy for validation)
  - Use `typing.Any` instead of builtin `any` for type annotations
  - Import types from `typing` module (e.g., `List`, `Dict`, `Optional`, `Any`)
- Follow shell best practices (shellcheck enforced)
- No unused imports or variables (autoflake enforced)
- Error handling: Use appropriate error classes and logging
- Write unit tests for new functionality (required for all new code)
- Design code to be testable: prefer pure functions and clear interfaces
- Documentation: Comments should explain "why", not "what" unless non-obvious
- Don't add comments above self-documenting code
- Maintain backwards compatibility with existing scripts
- For AWS resources, follow terraform best practices
- Never call functions within f-strings: create a variable first, then use it in the f-string
- Never use nested functions - always use class methods or module-level functions instead
- **When making a change based on feedback, search for similar patterns in the codebase** - if someone suggests a change that makes sense, check for other locations where the same improvement should be applied

## Testing Guidelines

- Tests are in `bin/test` and `lambda` directories with `_test.py` suffix
- Run tests with `make test` or `uv run pytest path/to/test.py`
- Test both success and error cases
- Mock external dependencies when appropriate
- **Always write tests for new functionality** - prefer testable code design
- Use pytest framework with descriptive test function names (e.g., `test_function_name_scenario`)
- Test files should import from `lib` modules directly
- Use `pytest.raises()` for exception testing with message matching
- Include both happy path and edge case scenarios
- Follow existing test patterns: simple functions, clear assertions, good docstrings

## Infrastructure Notes

This repository contains scripts and infrastructure configurations for Compiler Explorer.
Files in `/opt/compiler-explorer` are the target installation location.

## CLI Architecture

The CLI system (`bin/ce`) uses Click framework with a modular command structure:

- **Entry point**: `bin/ce` (shell script) → `bin/lib/ce.py` (Python entry)
- **Main CLI**: `bin/lib/ce_install.py` - defines the root CLI group and imports all command modules
- **Command modules**: Located in `bin/lib/cli/` directory
  - Each module defines commands using `@cli.command()` or command groups using `@cli.group()`
  - Commands are auto-discovered by importing all Python files in the CLI directory
  - Example: `environment.py` defines `ce environment refresh`, `ce environment status`, etc.

### Adding New CLI Commands

1. Create a new file in `bin/lib/cli/` or add to an existing module
2. Import the CLI object: `from lib.cli import cli`
3. Define commands using decorators:
   ```python
   @cli.command()
   @click.option("--flag", help="Description")
   @click.pass_obj
   def my_command(cfg: Config, flag: str):
       """Command description."""
       # Implementation
   ```
4. For grouped commands:
   ```python
   @cli.group()
   def mygroup():
       """Group description."""

   @mygroup.command()
   def subcommand():
       """Subcommand description."""
   ```

## GitHub Workflow Integration

The `ce workflows` command group provides functionality to trigger GitHub Actions workflows:

### Available Commands

- **`ce workflows run-discovery BUILDNUMBER`** - Trigger compiler discovery workflow in infra repo
  - Uses defaults: staging environment, main branch
  - Override with `--environment`, `--branch`, `--skip-remote-checks`
  - Example: `ce workflows run-discovery gh-12345 --environment prod`

- **`ce workflows deploy-win BUILDNUMBER`** - Trigger Windows deployment in main compiler-explorer repo
  - Uses defaults: main branch
  - Override with `--branch`
  - Example: `ce workflows deploy-win gh-12345 --branch release`

- **`ce workflows run REPO WORKFLOW [OPTIONS]`** - Generic workflow trigger for any CE repository
  - Pass parameters with `-f name=value` or `--field name=value`
  - Example: `ce workflows run compiler-explorer deploy-win.yml -f buildnumber=gh-12345 -f branch=main`

- **`ce workflows list`** - List available workflows across repositories

- **`ce workflows status [OPTIONS]`** - Show recent workflow run status
  - By default shows both infra and compiler-explorer repositories
  - Filter by `--repo` to show specific repository, `--workflow`, `--status`, `--branch`
  - Limit results with `--limit` (default: 10)
  - Examples:
    - `ce workflows status` (shows both repos)
    - `ce workflows status --repo infra --workflow compiler-discovery.yml`
    - `ce workflows status --status in_progress`

- **`ce workflows watch RUN_ID [OPTIONS]`** - View details of a specific workflow run
  - Use `--repo` to specify repository (default: infra)
  - Use `--job` to view specific job within the run
  - Use `--web` to open run in browser
  - Example: `ce workflows watch 15778532626 --web`

All workflow trigger commands support `--dry-run` to preview the `gh` command without executing it.

## AWS Integration Pattern

AWS clients are defined in `bin/lib/amazon.py` using lazy initialization:

```python
# Pattern for adding new AWS clients
from lib.amazon import LazyObjectWrapper, boto3

# Define lazy-loaded client
my_client = LazyObjectWrapper(lambda: boto3.client("service-name"))

# Use in code
my_client.some_method()  # Client is initialized on first use
```

### Key AWS Utilities

- **EC2/ASG**: `ec2`, `ec2_client`, `as_client` - for instance and auto-scaling management
- **S3**: `s3`, `s3_client`, `anon_s3_client` - for storage operations
- **ELB**: `elb_client` - for load balancer operations
- **DynamoDB**: `dynamodb_client` - for database operations
- **SSM**: `ssm_client` - for parameter store
- **CloudFront**: `cloudfront_client` - for CDN operations

### Common Patterns

- Configuration is passed via `Config` object containing environment (prod, beta, staging, etc.)
- Helper functions like `get_autoscaling_groups_for(cfg)` abstract common operations
- Error handling should use try/except with appropriate logging

## Testing Patterns

### Test Structure

- Test files mirror source structure: `bin/lib/foo.py` → `bin/test/foo_test.py`
- Use unittest.TestCase or plain pytest functions
- Mock AWS services and external dependencies

### Common Testing Patterns

1. **Mocking AWS Clients**:
   ```python
   @patch("lib.module.client_name")
   def test_function(self, mock_client):
       mock_client.method.return_value = {"key": "value"}
   ```

2. **Testing with Config**:
   ```python
   from lib.env import Config, Environment

   cfg = Config(env=Environment.PROD)
   ```

3. **Testing CLI Commands**:
   - Mock the underlying functions, not the Click command itself
   - Test the business logic separately from CLI parsing

4. **Common Assertions**:
   ```python
   # Check method was called
   mock_client.method.assert_called_once()
   mock_client.method.assert_called_with(param="value")

   # Check print output
   @patch("builtins.print")
   def test_output(self, mock_print):
       # ... code that prints ...
       print_calls = [call[0][0] for call in mock_print.call_args_list]
       assert any("expected text" in call for call in print_calls)
   ```

### Testing Best Practices

- Always test both success and failure cases
- Mock time-based operations for deterministic tests
- Use `pytest.raises()` for exception testing
- Keep tests focused and independent
- Name tests descriptively: `test_function_name_scenario`

## Environment Configuration

The codebase supports multiple environments defined in `lib/env.py`:
- `PROD`, `BETA`, `STAGING` - Main environments
- `GPU`, `RUNNER` - Specialized environments
- `WINPROD`, `WINSTAGING`, `WINTEST` - Windows environments
- `AARCH64PROD`, `AARCH64STAGING` - ARM environments

Each environment has properties like `keep_builds`, `is_windows`, `is_prod`, etc.

## Terraform Integration

- Infrastructure defined in `terraform/` directory
- CloudFront distributions, ALBs, ASGs, etc. are managed via Terraform
- When adding AWS resources that need IDs (like CloudFront distributions), consider:
  1. Getting IDs from Terraform outputs
  2. Hardcoding in configuration with clear documentation
  3. Dynamic lookup via AWS APIs
