# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Commands
- Setup: `make ce`
- Test: `make test` (single: `uv run pytest path/to/test.py::TestClass::test_method`)
- Static checks: `make static-checks` (run repeatedly until passes before committing)
- Lambda packages: `make lambda-package`, `make events-lambda-package`

## Code Style
- Python: Black (120 chars), mypy, type hints from `typing` module
- Shell: shellcheck enforced
- No unused imports/variables (autoflake)
- No nested functions, no function calls in f-strings
- Tests required for new functionality
- Comments explain "why" not "what"
- **When implementing feedback, search for similar patterns to update**

## Testing
- Location: `bin/test/`, `lambda/` with `_test.py` suffix
- Framework: pytest with descriptive names
- Mock AWS/externals, test success+failure cases
- Pattern: `bin/lib/foo.py` → `bin/test/foo_test.py`

## CLI Architecture
- Entry: `bin/ce` → `bin/lib/ce.py` → `bin/lib/ce_install.py`
- Commands in `bin/lib/cli/` using `@cli.command()` decorators
- Import: `from lib.cli import cli`

## AWS Integration
- Clients in `lib/amazon.py` with lazy initialization
- Pattern: `LazyObjectWrapper(lambda: boto3.client("service-name"))`
- Key clients: ec2, as_client, elb_client, s3, ssm_client, dynamodb_client, cloudfront_client
- Config via `Config` object with environment

## Infrastructure
- Target: `/opt/compiler-explorer`
- Terraform in `terraform/`
- Environments: PROD, BETA, STAGING, GPU, RUNNER, WIN*, AARCH64* (see `lib/env.py`)
