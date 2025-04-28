# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test/Lint Commands

- Setup environment: `make ce`
- Run all tests: `make test`
- Run a single test: `poetry run pytest bin/test/path_to_test.py::TestClass::test_method -v`
- Run static checks: `make static-checks`
- Check code style/linting: `make pre-commit`
- Install pre-commit hooks: `make install-pre-commit`
- Build lambda package: `make lambda-package`
- Build events lambda package: `make events-lambda-package`

## Important Workflow Requirements

- ALWAYS run pre-commit hooks before committing: `make pre-commit`
- The hooks will run tests and lint checks, and will fail the commit if there are any issues
- Failing to run pre-commit hooks may result in style issues and commit failures

## Code Style Guidelines

- Python formatting: Black with 120 char line length
- Use type hints for Python code (mypy for validation)
- Follow shell best practices (shellcheck enforced)
- No unused imports or variables (autoflake enforced)
- Error handling: Use appropriate error classes and logging
- Write unit tests for new functionality
- Documentation: Comments should explain "why", not "what" unless non-obvious
- Don't add comments above self-documenting code
- Maintain backwards compatibility with existing scripts
- For AWS resources, follow terraform best practices

## Testing Guidelines

- Tests are in `bin/test` and `lambda` directories with `_test.py` suffix
- Run tests with `make test` or `poetry run pytest path/to/test.py`
- Test both success and error cases
- Mock external dependencies when appropriate

## Infrastructure Notes

This repository contains scripts and infrastructure configurations for Compiler Explorer.
Files in `/opt/compiler-explorer` are the target installation location.
