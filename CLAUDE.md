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

## Terraform Guidelines

- When changing terraform .tf files, always run `terraform fmt` and `terraform validate` before committing (from the terraform directory)

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
  - Use `--wait` to wait for workflow completion
  - Example: `ce workflows run-discovery gh-12345 --environment prod --wait`

- **`ce workflows deploy-win BUILDNUMBER`** - Trigger Windows deployment in main compiler-explorer repo
  - Uses defaults: main branch
  - Override with `--branch`
  - Use `--wait` to wait for workflow completion
  - Example: `ce workflows deploy-win gh-12345 --branch release --wait`

- **`ce workflows run REPO WORKFLOW [OPTIONS]`** - Generic workflow trigger for any CE repository
  - Pass parameters with `-f name=value` or `--field name=value`
  - Use `--wait` to wait for workflow completion
  - Example: `ce workflows run compiler-explorer deploy-win.yml -f buildnumber=gh-12345 -f branch=main --wait`

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

## Compiler Routing Management

The `ce compiler-routing` command group provides functionality to manage compiler-to-queue routing mappings in DynamoDB:

### Available Commands

- **`ce compiler-routing update [--env ENVIRONMENT]`** - Update compiler routing table for specified environment using live API data
  - Uses current environment if not specified
  - Use `--dry-run` to preview changes without making them
  - Use `--skip-confirmation` to skip confirmation prompt
  - Example: `ce --env prod compiler-routing update --dry-run`

- **`ce compiler-routing status`** - Show current compiler routing table statistics
  - Displays total compilers, environments, routing types, and queue distribution
  - Example output shows prod (queue routing) vs winprod (URL routing)

- **`ce compiler-routing lookup COMPILER_ID`** - Look up routing assignment for a specific compiler
  - Shows environment, routing type (queue/url), and target (queue name or URL)
  - Uses current environment context
  - Example: `ce --env prod compiler-routing lookup gcc-trunk`

- **`ce compiler-routing validate [--env ENVIRONMENT]`** - Validate routing table consistency against live API data
  - Compares current table with live API data to identify needed changes
  - Validates specific environment or all environments
  - Example: `ce compiler-routing validate --env winprod`

- **`ce compiler-routing clear --env ENVIRONMENT`** - Clear routing entries for a specific environment
  - Removes all routing entries for the specified environment
  - Affected compilers fall back to default queue routing
  - Use `--skip-confirmation` to skip confirmation prompt
  - Example: `ce compiler-routing clear --env staging --skip-confirmation`


### Architecture Features

- **Environment Isolation**: Uses composite keys (e.g., `prod#gcc-trunk`) to prevent cross-environment conflicts
- **Hybrid Routing**: Supports both SQS queue routing and direct URL forwarding based on environment configuration
- **Backward Compatibility**: Legacy entries are supported during transition period
- **Multi-Environment Support**: Single DynamoDB table serves all environments (prod, staging, beta, winprod, etc.)

### Routing Strategies by Environment

- **Queue Environments**: prod, staging, beta → Route to SQS queues
- **URL Environments**: winprod, winstaging, wintest, gpu, aarch64prod, aarch64staging, runner → Forward directly to environment URLs

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

## Blue-Green Deployment Notifications

The blue-green deployment system includes GitHub notification functionality that automatically notifies PRs and issues when they go live in production.

### How It Works

- **Production Only**: Notifications are only sent when deploying to production environment
- **Version Change Detection**: Only notifies when there's an actual version change between deployments
- **Commit Range**: Checks commits between the current deployed version and the target version
- **GitHub Integration**: Uses GitHub API to find PRs linked to commits and issues linked to PRs
- **Automatic Labeling**: Adds 'live' label and "This is now live" comment to relevant PRs/issues

### Configuration

**Set GitHub Token**: Store GitHub API token in SSM Parameter Store:
```bash
aws ssm put-parameter \
  --name "/compiler-explorer/githubAuthToken" \
  --value "ghp_your_token_here" \
  --type "SecureString"
```

**Token Permissions**: GitHub token needs `repo`, `issues`, and `pull_requests` scopes

### Usage Examples

```bash
# Deploy with default notification behavior (interactive prompt on prod)
ce --env prod blue-green deploy gh-15725

# Force notifications on
ce --env prod blue-green deploy gh-15725 --notify

# Force notifications off
ce --env prod blue-green deploy gh-15725 --no-notify

# Dry-run mode - see what would be notified without sending
ce --env prod blue-green deploy gh-15725 --dry-run-notify

# Check what notifications would be sent without deploying
ce --env prod blue-green deploy gh-15725 --check-notifications

# Skip confirmation prompts
ce --env prod blue-green deploy gh-15725 --skip-confirmation
```

### Interactive Prompts

When deploying to production, the system prompts:
```
Send 'now live' notifications to GitHub issues/PRs? [yes/dry-run/no] (yes):
```

- **yes**: Sends actual notifications
- **dry-run**: Shows what would be notified without sending
- **no**: Skips notifications entirely

## Terraform Integration

- Infrastructure defined in `terraform/` directory
- CloudFront distributions, ALBs, ASGs, etc. are managed via Terraform
- When adding AWS resources that need IDs (like CloudFront distributions), consider:
  1. Getting IDs from Terraform outputs
  2. Hardcoding in configuration with clear documentation
  3. Dynamic lookup via AWS APIs
