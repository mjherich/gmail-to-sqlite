# Gmail-to-SQLite Project Guidelines

## Bash Commands
- `uv run gmail-to-sqlite sync`: Sync Gmail messages to database
- `uv run gmail-to-sqlite chat --model claude`: Start AI chat with Claude
- `uv run gmail-to-sqlite chat --model openai`: Start AI chat with OpenAI
- `uv run gmail-to-sqlite chat --model gemini`: Start AI chat with Gemini
- `uv run pytest`: Run test suite
- `uv run black .`: Format code with Black
- `uv run mypy .`: Run type checking
- `uv run flake8 .`: Run linting

## Code Style & Standards
- **Python Version**: 3.10+ required
- **Formatting**: Use Black with 88 character line length
- **Type Hints**: Always include type hints for function parameters and returns
- **Imports**: Use absolute imports, group standard library, third-party, then local imports
- **Error Handling**: Use specific exception types, include helpful error messages
- **Logging**: Use the `logging` module, set appropriate levels for different environments
- **Documentation**: Include docstrings for all public functions and classes

## Project Structure
- `gmail_to_sqlite/`: Main package directory
- `tests/`: Test files using pytest
- `pyproject.toml`: Project configuration and dependencies
- `settings.toml`: Application settings (use Dynaconf)
- `.secrets.toml`: API keys and sensitive data (not in git)

## CrewAI & AI Chat Guidelines
- **Model Configuration**: Support Gemini, OpenAI, and Claude models
- **API Keys**: Store in `.secrets.toml` using environment variable patterns:
  - `GOOGLE_API_KEY` for Gemini
  - `OPENAI_API_KEY` for OpenAI  
  - `ANTHROPIC_API_KEY` for Claude
- **Agent Design**: Use specific, specialized roles rather than generic ones
- **Task Descriptions**: Be clear, actionable, and include expected output format
- **Error Handling**: Include try-catch blocks for API calls with meaningful error messages
- **Context Management**: Use `respect_context_window=True` for large conversations

## Database Guidelines
- **ORM**: Use Peewee for database operations
- **Schema**: Messages table with JSON fields for sender/recipients
- **Migrations**: Place in `schema_migrations/` directory
- **Queries**: Support both SQL and natural language through AI agent

## Git Commit Message Format
Follow this pattern for all commits:

```
<Type>: <Brief description of what was accomplished>

<Detailed explanation of changes made, why they were needed, and impact>
<Include any breaking changes or migration steps if applicable>

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Commit Types:**
- **Fix**: Bug fixes and error corrections
- **Add**: New features or functionality
- **Update**: Improvements to existing features
- **Refactor**: Code restructuring without functional changes
- **Phase N**: Major milestone or feature completion

**Examples:**
- `Fix Claude model integration and upgrade to Claude Sonnet 4`
- `Add comprehensive AI chat improvement plan`
- `Phase 1: Enhanced Memory & Intelligent SQL Generation`

## Testing Guidelines
- **Test Coverage**: Aim for high test coverage, especially for core functionality
- **Test Organization**: Mirror the package structure in `tests/`
- **Fixtures**: Use pytest fixtures for common test data
- **Mocking**: Mock external APIs and services in tests
- **Database Testing**: Use temporary databases for integration tests

## Development Workflow
1. **Setup**: Install dependencies with `uv install`
2. **Development**: Make changes following code style guidelines
3. **Testing**: Run tests and ensure they pass
4. **Type Checking**: Run mypy to verify type annotations
5. **Formatting**: Run Black to format code
6. **Commit**: Use the standardized commit message format
7. **API Integration**: Test with actual API keys before pushing

## Configuration Management
- **Settings**: Use Dynaconf with `settings.toml` for app configuration
- **Secrets**: Store API keys in `.secrets.toml` (excluded from git)
- **Environment**: Support different configurations for dev/prod
- **Validation**: Validate required settings on startup

## Error Handling Best Practices
- **API Calls**: Always include timeout and retry logic
- **User Feedback**: Provide clear, actionable error messages
- **Logging**: Log errors with appropriate context
- **Graceful Degradation**: Fallback to simpler methods when AI fails
- **Validation**: Validate inputs early and provide helpful feedback

## AI Model Integration
- **Model Support**: Gemini (fast/cheap), OpenAI (balanced), Claude (most capable)
- **Fallbacks**: Always include fallback logic when AI fails
- **Rate Limiting**: Respect API rate limits and implement backoff
- **Context**: Provide sufficient context for accurate AI responses
- **Caching**: Cache common queries and responses when appropriate

## Planning & Research Artifacts
- **Workspace**: Use `.planning/` directory for all planning, research, and development artifacts
- **File Naming**: Use date-prefixed format `mm-dd-yy_description.ext` (e.g., `06-21-25_analysis.md`)
- **Purpose**: Store research findings, architecture diagrams, implementation plans, experiments, and any transient development artifacts
- **Git Handling**: Directory contents are gitignored to keep repository clean and focused on production code
- **Organization**: Files are self-organizing by date prefix for easy chronological sorting