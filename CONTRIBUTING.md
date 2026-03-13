# Contributing to DealRoom

First off, thank you for considering contributing to DealRoom! It's people like you that make DealRoom such a great real-time AI negotiation copilot.

## Code of Conduct

By participating in this project, you are expected to be welcoming, respectful, and collaborative.

## How Can I Contribute?

### Reporting Bugs
This section guides you through submitting a bug report for DealRoom. Following these guidelines helps maintainers and the community understand your report, reproduce the behavior, and find related reports.
* Use a clear and descriptive title for the issue to identify the problem.
* Describe the exact steps which reproduce the problem in as many details as possible.
* Describe the behavior you observed after following the steps and point out what exactly is the problem with that behavior.
* Explain which behavior you expected to see instead and why.

### Suggesting Enhancements
This section guides you through submitting an enhancement suggestion for DealRoom, including completely new features and minor improvements to existing functionality.
* Use a clear and descriptive title for the issue to identify the suggestion.
* Provide a step-by-step description of the suggested enhancement in as many details as possible.
* Explain why this enhancement would be useful to most DealRoom users.

### Pull Requests
Please follow these steps to have your contribution considered by the maintainers:
1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes (if applicable).
5. Ensure your code is formatted and lints correctly.
6. Issue that pull request!

## Setting Up Your Development Environment

### Prerequisites
- Python 3.9+
- A Google Gemini API Key

### Installation Steps

1. Clone your fork of the repository:
   ```bash
   git clone https://github.com/YOUR-USERNAME/DealRoom.git
   cd DealRoom
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   Create a `.env` file in the root directory and add your Google Gemini API key:
   ```bash
   echo 'GOOGLE_API_KEY=your_key' > .env
   ```

5. Run the application:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8080
   ```
   Open: `http://localhost:8080/overlay`

## Styleguides

### Git Commit Messages
* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line

### Python Styleguide
* Please follow PEP 8 for Python code.
* Use type hints where appropriate.
* Add docstrings to all functions and classes to explain their purpose.

### JavaScript Styleguide
* Use ES6+ syntax for the vanilla JS frontend.
* Ensure the floating overlay styling stays consistent and unintrusive.

## License

By contributing to DealRoom, you agree that your contributions will be licensed under the project's [LICENSE](LICENSE).
