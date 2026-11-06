
# Contributing to TradingBot

Thank you for your interest in contributing to TradingBot!

TradingBot is a research-first, offline-first Python futures trading framework. Contributions that improve reliability, testing, documentation, data validation and risk controls are welcome.

## Getting Started

Requirements:
- Python 3.12 or later
- Git

Clone the repository:

```bash
git clone https://github.com/sanketyadav2707-svg/TradingBot.git
cd TradingBot
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
pytest
```

Check the command-line interface:

```bash
python -m tradingbot --help
```

## Contribution Guidelines

1. Search existing issues before reporting a new problem.
2. Keep changes focused and easy to review.
3. Add regression tests for bug fixes.
4. Update documentation whenever behaviour or commands change.
5. Use deterministic and reproducible implementations.
6. Avoid look-ahead bias in historical research.
7. Never bridge calculations across missing data or contract rolls.
8. Keep risk and compliance controls separate from strategy logic.

## Security and Data Safety

- Never commit API keys, passwords, tokens or account credentials.
- Never upload private broker statements or personal financial information.
- Use properly licensed market data.
- Do not introduce live order execution or external broker connections without prior maintainer approval.
- Do not implement latency exploitation, stale-data exploitation or prop-firm rule bypasses.

## Research Contributions

Research proposals should document:

- Strategy hypothesis and precise entry/exit rules.
- Data source and licensing.
- Historical period and instrument.
- Commission and slippage assumptions.
- Training, validation and out-of-sample methodology.
- Limitations and reproducibility instructions.

Do not present simulated results as guaranteed or proven profitability.

## Pull Request Process

1. Create a separate branch for your changes.
2. Implement the proposed changes.
3. Run the automated test suite.
4. Update relevant documentation.
5. Submit a pull request with a clear explanation.
6. Respond to maintainer review feedback.

All contributions are subject to maintainer review.

Thank you for helping improve TradingBot!
