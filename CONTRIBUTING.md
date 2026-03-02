# Contributing to FastREST

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/anthropics/fastrest.git
cd fastrest
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

- Follow existing patterns in the codebase
- Keep the DRF-compatible API surface — don't break the public interface
- All new features should include tests
- Use type annotations

## Pull Requests

1. Fork the repo and create your branch from `main`
2. Add tests for any new functionality
3. Ensure the test suite passes
4. Submit a pull request

## Reporting Issues

Use [GitHub Issues](https://github.com/anthropics/fastrest/issues) to report bugs or request features. Include:
- Python version
- fastrest version
- Minimal reproduction code
- Expected vs actual behavior
