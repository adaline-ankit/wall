# Contributing

Thanks for helping build an information system that serves the reader rather than an engagement
algorithm.

## Start here

1. Open an issue for large features or architecture changes.
2. Fork the repository and create a focused branch.
3. Install with `pip install -e '.[dev]'`.
4. Add or update tests with behavior changes.
5. Run `ruff check .`, `mypy wall_harness`, and `pytest`.
6. Open a pull request explaining the user value, tradeoffs, and verification.

Keep the core local-first. New hosted integrations must be optional, document exactly what leaves
the machine, and fail with a useful message when credentials are absent. New ranking signals
should remain explainable through `RankedItem.reasons`.

By contributing, you agree that your contribution is licensed under the MIT License.
