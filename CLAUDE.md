# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication

When writing, especially PRs and commit messages:
- Avoid emojis
- Avoid "LLM tells", for example:
 - Don't use bullet items with `**Heading** - description`, unless it's _absolutely required for emphasis_
 - Avoid cliches
- Be terse but informative

## Build/Test/Lint Commands

- Setup environment: `make ce`
- Run all tests: `make test`
- Run a single test: `uv run pytest bin/test/path_to_test.py::TestClass::test_method -v`
- Run static checks: `make static-checks`
- Check code style/linting: `make pre-commit`
- Install pre-commit hooks: `make install-pre-commit`
- Build lambda package: `make lambda-package`
- Build events lambda package: `make events-lambda-package`
- **NEVER USE THE SYSTEM PYTHON** - always use `uv` to invoke python or pytest or to run experiments with python syntax

## Important Workflow Requirements

- ALWAYS run pre-commit hooks before committing: `make pre-commit`
- The hooks will run tests and lint checks, and will fail the commit if there are any issues. You will need to `git add` those changed files
- Failing to run pre-commit hooks may result in style issues and commit failures
- For comprehensive validation, run `make static-checks` before committing (includes all linting and type checking)
- If static checks fail, fix the issues before committing to avoid CI failures
- **Critical**: After fixing any issues, run `make static-checks` AGAIN. Repeat until it passes completely. Only commit when `make static-checks` runs with zero errors.
- If a python lint fails **DO NOT DISABLE IT**. The lint rules are there for a reason. You **MUST NOT** override them with `noqa` or similar. If you have no choice **YOU MUST GET EXPLICIT APPROVAL FROM THE USER**.

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
  - All Python files must include `from __future__ import annotations` at the top (after docstring)
  - Use modern Python 3.9+ typing syntax: `list[str]`, `dict[str, Any]`, `str | None` instead of `Optional[str]`
  - Only import `Any` from `typing` module when needed; use built-in types otherwise
  - Union types: use `X | Y` syntax instead of `Union[X, Y]`
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

## SQS Message Overflow to S3

The CE Router system supports automatic overflow of large compilation requests to S3 when they exceed SQS message size limits.

### Configuration

- **S3 Bucket**: `temp-storage.godbolt.org` (shared across all environments)
- **Message Storage**: Path pattern `sqs-overflow/{environment}/{timestamp}/{guid}.json`
- **Automatic Cleanup**: Messages deleted after 1 day (configurable via `sqs_overflow_retention_days` variable)
- **Server-side Encryption**: AES256 encryption enabled

### Environment Variables

Configure via SSM parameters:

- `SQS_MAX_MESSAGE_SIZE`: Maximum message size before overflow (bytes)
- `S3_OVERFLOW_BUCKET`: S3 bucket name (default: temp-storage.godbolt.org)
- `S3_OVERFLOW_KEY_PREFIX`: S3 key prefix (default: sqs-overflow/)

### IAM Permissions

The overflow system grants appropriate S3 permissions to:
- CE Router instances (write overflow messages)
- CE instances (read overflow messages)
- Lambda functions (read/write overflow messages)

### Monitoring

- CloudWatch metric `SQSOverflowMessages` tracks overflow usage
- CloudWatch alarm triggers when more than 100 messages overflow in 5 minutes

## Instance Management

The `ce instances` command group provides functionality to manage CE instances:

### Available Commands

- **`ce instances isolate`** - Isolate an instance for investigation
  - Enables stop and termination protection on the EC2 instance
  - Puts instance into standby mode (removes from ASG rotation)
  - Deregisters from load balancer (stops serving traffic)
  - Instance remains accessible via SSH for debugging
  - Instance appears in `ce instances status` as "Isolated"
  - Example: `ce --env staging instances isolate`

- **`ce instances terminate-isolated`** - Terminate an isolated instance
  - Only works on instances in Standby state
  - Removes stop and termination protection
  - Terminates the instance (ASG will automatically replace it)
  - Example: `ce --env staging instances terminate-isolated`

- **`ce instances status`** - Show all instances including isolated ones
  - Shows active instances registered with load balancer
  - Shows isolated instances in Standby state
  - Example: `ce --env prod instances status`

- **`ce instances restart`** - Rolling restart of all instances
- **`ce instances restart_one`** - Restart a single instance
- **`ce instances login`** - SSH into an instance
- **`ce instances exec_all`** - Execute command on all instances

### Isolation Use Cases

Use instance isolation when you need to:
- Debug production issues without affecting traffic
- Investigate memory leaks or performance problems
- Analyze core dumps or logs
- Test fixes before applying to all instances

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

## CE Router Management

The `ce ce-router` command group provides emergency controls for the CE Router routing system:

### Available Commands

- **`ce ce-router exec_all REMOTE_CMD`** - Execute commands on all CE Router instances
  - Runs the specified command on all CE Router instances in the current environment
  - Requires confirmation before execution
  - Example: `ce --env prod ce-router exec_all uptime`
  - Example: `ce --env prod ce-router exec_all cat /infra/.deploy/ce-router-version`

- **`ce ce-router version`** - Show installed CE Router version on all instances
  - Displays the version from `/infra/.deploy/ce-router-version` on each instance
  - Example: `ce --env prod ce-router version`

- **`ce ce-router refresh`** - Refresh CE Router instances with latest version
  - Performs a rolling instance refresh via AWS Auto Scaling Group
  - Launches new instances, waits for health checks, then terminates old instances
  - Maintains minimum healthy percentage during update (default: 75%)
  - Monitors progress and shows completion status
  - Use `--min-healthy-percent` to adjust safety threshold
  - Use `--skip-confirmation` to skip confirmation prompt
  - Example: `ce --env prod ce-router refresh`
  - Example: `ce --env prod ce-router refresh --min-healthy-percent 90`

- **`ce ce-router disable ENVIRONMENT`** - Disable CE Router ALB routing for an environment
  - Immediately stops routing compilation requests through CE Router
  - Falls back to legacy instance-based routing within seconds
  - Environments: beta, staging, prod
  - Use `--skip-confirmation` to skip confirmation prompt
  - Example: `ce ce-router disable beta`

- **`ce ce-router enable ENVIRONMENT`** - Re-enable CE Router ALB routing for an environment
  - Restores routing of compilation requests through CE Router
  - Takes effect immediately after ALB rule modification
  - Use `--skip-confirmation` to skip confirmation prompt
  - Example: `ce ce-router enable beta`

- **`ce ce-router status [ENVIRONMENT]`** - Show current status of CE Router ALB routing
  - Shows actual ALB listener rule state (not Terraform configuration)
  - Status indicators:
    - 🟢 ENABLED: CE Router routing active
    - 🚨 KILLSWITCH ACTIVE: Using instance routing
    - 🔴 NOT_FOUND: No ALB rule exists
  - Without environment argument, shows status for all environments
  - Example: `ce ce-router status` or `ce ce-router status prod`

### Version Management

CE Router software is downloaded from GitHub releases on instance startup. The installed version is saved to `/infra/.deploy/ce-router-version`.

**Check installed version**:
```bash
ce --env prod ce-router exec_all cat /infra/.deploy/ce-router-version
```

**Check latest available version**:
```bash
ce --env prod ce-router exec_all "curl -s https://api.github.com/repos/compiler-explorer/ce-router/releases/latest | jq -r '.tag_name'"
```

**Update to latest version**:
```bash
ce --env prod ce-router refresh
```

This performs a rolling update, launching new instances with the latest CE Router version from GitHub releases, then terminating old instances once the new ones are healthy.

### Usage Scenarios

**Emergency Response**: Use killswitch when Lambda compilation system is experiencing issues:
```bash
# Disable CE Router routing for production
ce ce-router disable prod

# Check status across all environments
ce ce-router status

# Re-enable when issues are resolved
ce ce-router enable prod
```

### Technical Details

- Modifies ALB listener rules directly (bypasses Terraform)
- Changes take effect immediately without deployment
- Killswitch works by changing path patterns to never match
- Enable restores original path patterns for the environment

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

## Go Standard Library Management

### Automatic Building During Installation

When installing Go compilers using the `go` installer type (configured in `bin/yaml/go.yaml`), the standard library is automatically built during the staging phase:

- Default architectures: `linux/amd64`, `linux/arm64`
- Cache directory: `<go-installation>/cache`
- Marker files: `.built_linux_amd64`, `.built_linux_arm64` (stored in cache directory)
- Controlled by YAML properties:
  - `build_stdlib: true/false` - Enable/disable automatic building (default: true)
  - `build_stdlib_archs: [...]` - List of architectures to build

### Architecture

- Standard library cache is stored in `cache` subdirectory of Go installation
- Per-architecture marker files track build status (e.g., `.built_linux_amd64`)
- Builds use Go's native `go build std` command with `GOCACHE` environment variable
- Builds are idempotent: existing builds are detected via marker files
- Core logic in `bin/lib/golang_stdlib.py`, installer in `bin/lib/installable/go.py`

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

## Blue-Green Deployment Process

The blue-green deployment system includes automatic post-deployment steps that ensure the environment is fully configured.

### Deployment Steps

1. **Version Setting**: Updates the deployed version (if specified)
2. **Scale Up**: Scales the inactive ASG to target capacity
3. **Health Checks**: Waits for instances to be healthy
4. **Traffic Switch**: Switches load balancer traffic to new instances
5. **Scale Down Protection**: Resets ASG minimum sizes
6. **Compiler Routing Update**: Automatically updates the compiler routing table for the environment
7. **GitHub Notifications**: Sends notifications for production deployments (when enabled)

### Compiler Routing Integration

After successful deployment, the system automatically runs `compiler-routing update` for the deployed environment:

- **Automatic**: No manual intervention required
- **Environment-specific**: Only updates routing for the deployed environment
- **Safe**: Deployment continues even if routing update fails (with warning)
- **Informative**: Shows count of added/updated/deleted routing entries

### Color-Specific Queue Routing

The blue-green deployment system uses color-specific SQS queues to prevent queue consumption overlap:

- **Instance Color Detection**: Instances automatically detect their color from EC2 instance tags (`Color` tag)
- **Startup Parameter Passing**: `init/start.sh` and `start.ps1` pass `--instance-color` to Node.js when color is detected
- **Queue Separation**: Blue instances consume from blue queues, green instances consume from green queues
- **Lambda Routing**: Compilation Lambda routes requests to the active color's queue based on SSM parameter

### GitHub Notification System

The deployment system includes GitHub notification functionality that automatically notifies PRs and issues when they go live in production.

#### How It Works

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

## CE Install Filter System

The `ce_install` command supports a filter system to narrow down installables. Filter syntax and usage patterns are documented in `docs/filter-system.md`.

## Terraform Integration

- Infrastructure defined in `terraform/` directory
- CloudFront distributions, ALBs, ASGs, etc. are managed via Terraform
- When adding AWS resources that need IDs (like CloudFront distributions), consider:
  1. Getting IDs from Terraform outputs
  2. Hardcoding in configuration with clear documentation
  3. Dynamic lookup via AWS APIs
