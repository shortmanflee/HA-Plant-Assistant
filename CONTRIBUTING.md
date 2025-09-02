# Contributing to Your Home Assistant Integration

Thank you for your interest in contributing to this Home Assistant integration! This document provides guidelines for contributing to an integration built from this template.

## Getting Started

This integration was built using the [HA-Integration-Template](https://github.com/shortmanflee/HA-Integration-Template). If you're creating your own integration from this template, please update this file with your specific contribution guidelines.

## Types of Contributions

We welcome various types of contributions:

- 🐛 **Bug Reports**: Help us identify and fix issues
- 💡 **Feature Requests**: Suggest new functionality
- 🔧 **Code Contributions**: Submit bug fixes or new features
- 📝 **Documentation**: Improve or add documentation
- 🧪 **Testing**: Add or improve test coverage

## Development Environment

### 🐳 Recommended: DevContainer Setup

The easiest and most reliable way to set up the development environment is using the included devcontainer:

#### DevContainer Prerequisites

- [VS Code](https://code.visualstudio.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

#### Setup Steps

1. **Fork and Clone**:

   ```bash
   git clone https://github.com/yourusername/your-integration-name.git
   cd your-integration-name
   ```

2. **Open in VS Code**:

   ```bash
   code .
   ```

3. **Start DevContainer**:
   - VS Code will detect the devcontainer configuration
   - Click "Reopen in Container" when prompted
   - Or use Command Palette: `Dev Containers: Reopen in Container`

4. **Automatic Setup**: The devcontainer will automatically:
   - Set up Python 3.13 environment with virtual environment
   - Install all dependencies from `requirements.txt`
   - Configure the development environment
   - Install recommended VS Code extensions
   - Forward port 8080 for Home Assistant

5. **Ready to Develop**: Everything is pre-configured and ready to use!

### 💻 Alternative: Local Development

If you prefer not to use containers:

#### Local Development Prerequisites

- Python 3.11+
- Home Assistant development environment
- Git

#### Setup

1. **Fork and Clone**:

   ```bash
   git clone https://github.com/yourusername/your-integration-name.git
   cd your-integration-name
   ```

2. **Create Virtual Environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   ```

3. **Install Dependencies**:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Setup Development Environment**:

   ```bash
   mkdir -p config
   ln -sf $(pwd)/custom_components config/custom_components
   ```

### Using VS Code

This project includes VS Code tasks for common development operations:

- **Install Dependencies**: Set up the Python environment
- **Start Home Assistant (Development)**: Launch HA with the integration
- **Run Tests**: Execute the test suite
- **Lint and Fix with Ruff**: Format and check code quality

## Making Changes

### Branch Strategy

1. Create a feature branch from `main`:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit with clear messages:

   ```bash
   git commit -m "Add: new feature description"
   ```

3. Push and create a pull request:

   ```bash
   git push origin feature/your-feature-name
   ```

### Code Standards

We use **Ruff** for code formatting and linting, along with other quality tools via pre-commit hooks:

```bash
# Format code
ruff format .

# Check for issues
ruff check .

# Auto-fix issues where possible
ruff check . --fix
```

#### Pre-commit Workflow

This project uses pre-commit hooks to automatically fix common code quality issues:

**How it Works:**

1. **Make your changes** and stage them with `git add`
2. **Attempt to commit** with `git commit -m "your message"`
3. **If auto-fixes are applied:**
   - The commit will be blocked
   - Review changes with `git diff`
   - Stage approved changes with `git add .` or selectively
   - Commit again with `git commit -m "your message"`

**Manual Fix Commands:**

```bash
# Fix all issues at once
npm run precommit:fix

# Fix specific types of issues
npm run lint:markdown:fix
source .venv/bin/activate && ruff --config .linter/ruff.toml format . && ruff --config .linter/ruff.toml check . --fix
```

**What Gets Auto-Fixed:**

- ✅ **Python**: Code formatting, import sorting, basic linting issues (Ruff)
- ✅ **Markdown**: Formatting, style consistency (markdownlint)
- ✅ **YAML**: Formatting, indentation (Prettier)
- ✅ **General**: Trailing whitespace, missing final newlines
- ❌ **Manual Review Required**: Type errors, security issues, spelling mistakes

**Important Notes:**

- **Always review auto-fixes** before committing
- **Auto-fixes are not automatically staged** - you must review and stage them
- **Some issues require manual intervention** (type errors, security, spelling)
- **Use `git diff` to see what was changed** by the auto-fixes

**Code must pass all linting checks before being merged.**

### Testing

All contributions should include appropriate tests:

```bash
# Run all tests
python -m pytest tests/ -v

# Run tests with coverage
python -m pytest tests/ -v --cov=custom_components
```

**Requirements:**

- All new features must include tests
- Bug fixes should include regression tests
- Aim for high test coverage (>80%)
- All tests must pass before merging

### Documentation

When adding new features:

1. Update docstrings for all new functions/classes
2. Add type hints where appropriate
3. Update README.md if the public API changes
4. Consider adding examples for complex features

## Pull Request Process

1. **Before Submitting**:
   - [ ] Code is properly formatted with Ruff
   - [ ] All tests pass
   - [ ] Documentation is updated
   - [ ] Commit messages are clear and descriptive

2. **PR Description**:
   - Clearly describe what the PR does
   - Reference any related issues
   - Include screenshots for UI changes
   - List any breaking changes

3. **Review Process**:
   - PRs require at least one review
   - Address all feedback before merging
   - Keep PRs focused and reasonably sized

## Reporting Issues

When reporting bugs, please include:

### Bug Reports

**Use the bug report template and include:**

- **Environment Details**:
  - Home Assistant version
  - Integration version
  - Python version
  - Operating system

- **Steps to Reproduce**:
  1. Be specific and detailed
  2. Include configuration examples
  3. Provide sample code if relevant

- **Expected vs Actual Behaviour**:
  - What should have happened?
  - What actually happened?

- **Logs and Error Messages**:
  - Include relevant log entries
  - Enable debug logging if possible
  - Sanitize sensitive information

### Feature Requests

**For new features, please include:**

- Clear description of the proposed feature
- Use case and motivation
- Potential implementation approach
- Any breaking changes considerations

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Assume good intentions

### Unacceptable Behaviour

- Harassment or discriminatory language
- Personal attacks or trolling
- Spam or off-topic discussions
- Publishing private information

## Development Resources

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Integration Development Guide](https://developers.home-assistant.io/docs/creating_component_index/)
- [Home Assistant Architecture](https://developers.home-assistant.io/docs/architecture/)
- [Testing Guidelines](https://developers.home-assistant.io/docs/development_testing/)

## Questions or Help?

- Check existing issues and discussions
- Review the Home Assistant developer documentation
- Ask questions in GitHub Discussions
- Join the Home Assistant Discord community

## License

By contributing, you agree that your contributions will be licensed under the same license as this project (MIT License).

---

Thank you for helping make this integration better! 🚀
