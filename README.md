# Home Assistant Integration Template

A comprehensive template repository for developing Home Assistant custom integrations with best practices, testing, and development environment pre-configured.

## Features

- 🏗️ **Complete Integration Structure**: Pre-configured directory structure following Home Assistant standards
- 🐳 **DevContainer Ready**: Full VS Code devcontainer setup with Python 3.13, dependencies, and extensions pre-installed
- 🧪 **Testing Setup**: Includes pytest configuration with Home Assistant custom component testing
- 🔧 **Development Environment**: VS Code tasks and configuration for seamless development
- 📋 **Code Quality**: Ruff linting and formatting pre-configured
- 🐳 **HACS Ready**: Includes `hacs.json` configuration for Home Assistant Community Store
- 📝 **Documentation**: Template files and contribution guidelines

## Quick Start

### Using This Template

1. Click "Use this template" button on GitHub
2. Create your new repository from this template
3. Clone your new repository:

   ```bash
   git clone https://github.com/yourusername/your-integration-name.git
   cd your-integration-name
   ```

4. **🐳 Recommended**: Open in VS Code and use the devcontainer:
   - Open VS Code: `code .`
   - Click "Reopen in Container" when prompted
   - Everything will be automatically configured!

### Customizing Your Integration

1. **Rename the integration directory**:

   ```bash
   mv custom_components/integration_template custom_components/your_integration_name
   ```

2. **Update the integration files**:
   - Edit `custom_components/your_integration_name/__init__.py`
   - Update `hacs.json` with your integration details
   - Modify `README.md` for your specific integration

3. **Update repository references**:
   Run the provided task to update all references:

   ```bash
   ./.vscode/dependencies/update_repo_references.sh
   ```

## Development Environment

This template provides two development approaches, with **devcontainer being the recommended method** for the best development experience.

### 🐳 Recommended: DevContainer (VS Code)

The easiest way to get started is using the included devcontainer configuration:

1. **Prerequisites**:
   - [VS Code](https://code.visualstudio.com/)
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

2. **Setup**:
   - Open the repository in VS Code
   - When prompted, click "Reopen in Container" (or use Command Palette: "Dev Containers: Reopen in Container")
   - The devcontainer will automatically:
     - Set up Python 3.13 environment
     - Install all dependencies
     - Configure the development environment
     - Install recommended VS Code extensions

3. **Ready to develop**: Everything is pre-configured and ready to use!

### 💻 Alternative: Local Development

If you prefer local development without containers:

#### Prerequisites

- Python 3.11+
- Virtual environment (recommended)

#### Setup

1. **Create and activate virtual environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   # or
   .venv\Scripts\activate     # On Windows
   ```

2. **Install dependencies**:
   Use the VS Code task "Install Dependencies" or run:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Setup development environment**:
   Use the VS Code task "Setup Config Directory" or run:

   ```bash
   mkdir -p config
   ln -sf $(pwd)/custom_components config/custom_components
   ```

### Available VS Code Tasks

- **Install Dependencies**: Install all required Python packages
- **Start Home Assistant (Development)**: Launch HA with your integration in debug mode
- **Setup Config Directory**: Configure the development environment
- **Run Tests**: Execute the test suite with pytest
- **Lint and Fix with Ruff**: Format and lint your Python code
- **Lint Markdown**: Check markdown files for formatting issues
- **Fix Markdown**: Automatically fix markdown formatting issues
- **Lint All (Python + Markdown)**: Run both Python and Markdown linting
- **Update Repository References**: Update template references to your integration

### Running Home Assistant

Start Home Assistant in development mode:

```bash
hass --config ./config --debug
```

Your integration will be available at `http://localhost:8080`

## Testing

Run tests using pytest:

```bash
python -m pytest tests/ -v
```

The template includes:

- Test configuration in `pyproject.toml`
- Coverage reporting
- Async test support
- Home Assistant custom component testing utilities

## Code Quality

This template includes comprehensive linting and code quality tools that run both locally and in CI/CD:

### 🔧 Available Linters

All linter configurations are stored in the `.linter/` directory:

- **Ruff** (`.linter/ruff.toml`): Fast Python linter and formatter
- **MyPy** (`.linter/mypy.ini`): Static type checking for Python
- **Pylint** (`.linter/pylintrc`): Additional Python code analysis
- **Bandit** (built-in): Security vulnerability scanner
- **yamllint** (`.linter/yamllint`): YAML file linting
- **markdownlint** (`.linter/.markdownlint.jsonc`): Markdown formatting
- **CSpell** (`.linter/cspell.json`): Spell checking across all files

### 🚀 Running Linters Locally

#### Quick Commands

```bash
# Format and lint Python code
source .venv/bin/activate && ruff --config .linter/ruff.toml format . && ruff --config .linter/ruff.toml check . --fix

# Type checking
mypy --config-file .linter/mypy.ini custom_components/

# Security scan
bandit -r custom_components/

# YAML linting
yamllint --config-file .linter/yamllint .

# Markdown linting
npm run lint:markdown

# Spell checking
npm run spell:check
```

#### VS Code Tasks

Use the Command Palette (`Ctrl+Shift+P`) and run:

- **Full Lint Suite**: Runs all linters (Ruff, MyPy, Bandit, YAML, Markdown, Spell check)
- **Enhanced Full Lint Suite**: Includes additional tools (Pylint, dead code detection, docstring checks)
- **Lint and Fix with Ruff**: Python formatting and linting
- **Lint Markdown**: Markdown file checking
- **Type Check with MyPy**: Static type analysis
- **Security Check with Bandit**: Vulnerability scanning

### 🤖 GitHub Actions CI/CD

All linters automatically run on every push and pull request via GitHub Actions (`.github/workflows/lint.yml`):

- ✅ **Ruff** - Code formatting and linting
- ✅ **MyPy** - Type checking
- ✅ **Pylint** - Additional Python analysis
- ✅ **Bandit** - Security scanning
- ✅ **yamllint** - YAML validation
- ✅ **markdownlint** - Markdown formatting
- ✅ **CSpell** - Spell checking

The CI runs on Python 3.13 and ensures all code meets quality standards before merging.

### 📝 Configuration Notes

- **Ruff**: Based on Home Assistant core configuration, includes all checks with integration-specific exclusions
- **MyPy**: Configured for strict type checking with Home Assistant imports handled
- **yamllint**: Configured to work with GitHub Actions workflows and excludes `node_modules/` and `.venv/`
- **CSpell**: Includes common Home Assistant terms and technical vocabulary
- **markdownlint**: Allows HTML and flexible line lengths for documentation

## Markdown linting

```bash
npm run lint:markdown:fix
```

### Pre-commit Hooks

Pre-commit hooks are automatically installed in the devcontainer and will run both Python and Markdown linting before each commit:

```bash
# Manually run pre-commit on all files
pre-commit run --all-files
```

## Directory Structure

```text
your-integration/
├── custom_components/
│   └── your_integration_name/
│       ├── __init__.py          # Integration entry point
│       ├── manifest.json        # Integration metadata
│       └── ...                  # Your integration files
├── tests/                       # Test files
├── config/                      # Development HA config
├── .vscode/                     # VS Code configuration
├── requirements.txt             # Python dependencies
├── pyproject.toml              # Project configuration
├── hacs.json                   # HACS configuration
└── README.md                   # This file
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to your integration.

## License

This template is released under the MIT License. See [LICENSE](LICENSE) for details.

## Resources

- [Home Assistant Developer Documentation](https://developers.home-assistant.io/)
- [Home Assistant Architecture](https://developers.home-assistant.io/docs/architecture/)
- [Integration Development](https://developers.home-assistant.io/docs/creating_component_index/)
- [HACS Documentation](https://hacs.xyz/docs/publish/start)

## Acknowledgements

This repo has been adapted from the [Integration Blueprint](https://github.com/ludeeus/integration_blueprint) repo maintained by [ludeeus](https://github.com/ludeeus).
