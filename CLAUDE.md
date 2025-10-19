# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`egauge-async` is an async Python client library for communicating with eGauge energy monitoring meters via their XML API. The library provides both low-level data access and high-level convenience methods for common operations like fetching current rates and calculating interval changes.

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv
uv sync
```

### Testing
```bash
# Run all tests with coverage
uv run pytest --cov=egauge_async

# Run a single test file
uv run pytest test/test_client.py

# Run a specific test
uv run pytest test/test_client.py::test_get_instantaneous_data

# Run only unit tests (exclude integration tests)
uv run pytest -m "not integration"

# Run only integration tests (requires real eGauge device)
uv run pytest -m integration
```

### Integration Testing

Integration tests run against a real eGauge device to validate end-to-end functionality. These tests are located in `test/json/test_json_client_integration.py` and marked with `@pytest.mark.integration`.

#### Setup

Before running integration tests, set these environment variables:

```bash
export EGAUGE_URL="https://egauge12345.local"  # Your eGauge device URL
export EGAUGE_USERNAME="owner"                 # Username for authentication
export EGAUGE_PASSWORD="your_password"         # Device password
```

#### Running Integration Tests

```bash
# Run all integration tests
uv run pytest -m integration

# Run specific integration test
uv run pytest -m integration -k "test_auth_successful_login"

# Run with verbose output
uv run pytest -m integration -v
```

#### Integration Test Coverage

The integration test suite validates:

- **Authentication & Token Management**: Login, token caching, token refresh, concurrent requests
- **Register Information**: Metadata fetching, caching, data structure validation
- **Current Measurements**: All registers, filtered queries, error handling
- **Historical Data**: Time-range queries, register filtering, quantum conversion, timestamp ordering
- **Error Handling**: Invalid credentials, unknown registers, token invalidation recovery
- **Data Consistency**: Register name consistency across endpoints

#### Notes

- Integration tests automatically skip if environment variables are not set
- Tests use SSL verification disabled (eGauges use self-signed certificates)
- Tests are read-only and do not modify device state
- Tests work with any eGauge device without assumptions about specific registers
- Default test runs (`pytest`) exclude integration tests; use `-m integration` to run them

### Code Quality
```bash
# Run ruff linter (check only)
uv run ruff check

# Run ruff formatter (check only)
uv run ruff format --check

# Auto-fix linting issues
uv run ruff check --fix

# Auto-format code
uv run ruff format

# Run pyright type checker
uv run pyright
```

### Pre-commit Hooks
This project uses pre-commit hooks for ruff linting and formatting. These run automatically on commit.

### Building
```bash
# Build distribution packages
uv build
```

## Git and GitHub Workflow

### Branch Strategy

- **Always create feature branches**: Develop new features, bug fixes, and experiments in dedicated branches created from `main`
- **Use descriptive branch names**: e.g., `json-client`, `fix-timeout-error`, `add-rate-calculation`
- **Keep branches focused**: One feature or fix per branch for easier review and rollback

### Commit Practices

- **Make atomic commits**: Each commit should represent a single logical change that could be reverted independently
- **Write meaningful commit messages**:
  - Use imperative mood ("Add feature" not "Added feature")
  - Focus on why the change was made, not just what changed
  - First line is a concise summary, followed by detailed explanation if needed
- **Commit frequently**: Small, incremental commits are easier to review and debug than large monolithic ones
- **Never commit broken code**: Each commit should leave the codebase in a working state

### Pull Request Workflow

- **Ensure quality before creating PR**: All tests pass, code is formatted, type checking succeeds
- **Write descriptive PR descriptions**: Explain the motivation, approach, and any trade-offs
- **Keep PRs focused and reviewable**: Large PRs are hard to review; break work into smaller, logical PRs when possible
- **Target `main` branch**: Unless working on a long-lived feature branch, PRs should merge into `main`
- **Address review feedback promptly**: Make requested changes in new commits for transparency
- **Squash when appropriate**: Consider squashing fix-up commits before merging to keep history clean

### General Guidelines

- **Pull before you push**: Always fetch and merge `main` into your branch before pushing to avoid conflicts
- **Don't force push to shared branches**: Rewrites history and causes problems for collaborators
- **Use draft PRs for early feedback**: Mark PRs as draft when seeking early input on approach
- **Link issues in commits and PRs**: Reference related issues with `#issue-number` for traceability

## Architecture

### Core Components

**EgaugeClient** (`egauge_async/client.py`): The main client class that provides async access to eGauge devices.
- Uses `httpx.AsyncClient` for HTTP requests with digest authentication support
- Disables SSL verification since eGauges use self-signed certificates
- Provides two main endpoints:
  - Instantaneous data: `/cgi-bin/egauge` - current snapshot with rates
  - Historical data: `/cgi-bin/egauge-show` - stored time-series data

**Data Models** (`egauge_async/data_models.py`):
- `RegisterData`: Individual register reading with type code, value, and optional rate
- `DataRow`: Timestamp + dictionary of register data
- `TimeInterval`: Enum for time intervals (SECOND, MINUTE, HOUR, DAY)

**Parsing Strategy**: The client separates concerns by having static `_parse_*` methods that handle XML parsing independently from HTTP requests. This makes testing easier and allows for mocking parsers separately from network calls.

### Key Design Patterns

1. **Lazy Register Discovery**: Methods like `get_instantaneous_registers()` and `get_historical_registers()` cache results after first call to avoid repeated network requests.

2. **Query String Building**: Custom query string utility (`utils.create_query_string()`) supports value-less parameters required by the eGauge API (e.g., `?inst&tot`).

3. **Interval Changes Calculation**: The `get_interval_changes()` method retrieves historical data points and computes deltas between consecutive timestamps, useful for energy consumption calculations.

4. **Register Name Discrepancy**: Be aware that computed registers may have different names in instantaneous vs. historical endpoints (e.g., "Total Usage" vs. "use").

### Testing Approach

Tests use mock HTTP clients that validate:
- URL construction (scheme, netloc, path, query parameters)
- Response parsing logic (separate from network calls)
- Async behavior with pytest-asyncio

The `MockAsyncClient` class in tests validates that query parameters are correctly formatted without actually making network requests.

## Coding Standards

### Type Safety and Data Structures

- **Prefer dataclasses over tuples/dicts for return values**: When a function returns multiple related values, use a dataclass instead of a tuple or dict. This provides better type safety, self-documentation, and IDE support.
  - ❌ Bad: `def parse_response() -> Tuple[str, str]`
  - ✅ Good: `def parse_response() -> ResponseData` (where ResponseData is a dataclass)
- **Use strict type checking**: All code must pass `pyright` in strict mode with no errors
- **Type all function parameters and return values**: Even when types are obvious

### Testing

- Follow TDD principles: write tests first, see them fail, then implement
- Use descriptive test names that explain what is being tested
- Mock at the HTTP client level, not the parsing level
- Separate parsing tests from integration tests

## Important Notes

- Python 3.11+ required
- All async methods should be properly awaited
- The client's `close()` method should be called to clean up the HTTP session (or use as async context manager pattern if implemented)
- Version is dynamically set via uv-dynamic-versioning from git tags
