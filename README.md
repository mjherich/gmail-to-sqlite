# Gmail to SQLite

A robust Python application that syncs Gmail messages to a local SQLite database for analysis and archival purposes.

## Features

- **Incremental Sync**: Only downloads new messages by default
- **Full Sync**: Option to download all messages and detect deletions
- **Parallel Processing**: Multi-threaded message fetching for improved performance
- **Robust Error Handling**: Automatic retries with exponential backoff
- **Graceful Shutdown**: Handles interruption signals cleanly
- **Type Safety**: Comprehensive type hints throughout the codebase
- **AI-Powered Chat**: Interactive chat interface and natural language queries about your emails using OpenAI
- **Interactive Chat**: Multi-turn conversational interface with CrewAI agents for email analysis

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 credentials file (`credentials.json`)
- OpenAI API key (for AI query features)

### Setup

#### Option 1: Global Installation with uv (Recommended)

```bash
# Install from source with uv tool install (package not yet on PyPI)
git clone https://github.com/marcboeker/gmail-to-sqlite.git
cd gmail-to-sqlite
uv tool install .
```

**Note**: `uv tool install` automatically handles dependency resolution with the correct versions from the lock file. This is the modern replacement for pipx.

#### Option 2: Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/marcboeker/gmail-to-sqlite.git
   cd gmail-to-sqlite
   ```

2. **Install dependencies:**

   ```bash
   # Using uv
   uv sync
   ```

#### Common Setup (Both Options)

1. **Set up Gmail API credentials:**

   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials file and save it as `credentials.json` in the project root directory

2. **Set up AI API keys (for chat features):**

   The application supports multiple AI models: OpenAI GPT-4o, Google Gemini, and Anthropic Claude. You need at least one API key to use the chat functionality.

   ```bash
   # Copy the example file and add your actual configuration
   cp .secrets.toml.example .secrets.toml
   # Edit .secrets.toml with your actual data directory and API keys
   ```

   The `.secrets.toml` file should contain:

   ```toml
   # Data directory where SQLite database and credentials will be stored
   DATA_DIR = "/path/to/your/gmail-data"

   # At least one of these is required for chat functionality
   OPENAI_API_KEY = "your-openai-api-key-here"       # Get from: https://platform.openai.com/api-keys
   GOOGLE_API_KEY = "your-google-api-key-here"       # Get from: https://aistudio.google.com/app/apikey
   ANTHROPIC_API_KEY = "your-anthropic-api-key-here" # Get from: https://console.anthropic.com/
   ```

## Usage

### Configuration

The application loads configuration from `.secrets.toml` and `settings.toml` files in the project directory. This allows the CLI to work from **any directory** while finding your configuration automatically.

```bash
# Set up data directory and API keys using the secrets file
cd /path/to/gmail-to-sqlite
cp .secrets.toml.example .secrets.toml
# Edit .secrets.toml with your actual data directory and API keys

# You can now run from anywhere!
gmail-to-sqlite sync
```

### Basic Commands

If you installed with uv tool install (global installation):

```bash
# Incremental sync (default) - reads data directory from .secrets.toml
gmail-to-sqlite sync

# Full sync with deletion detection
gmail-to-sqlite sync --full-sync

# Sync a specific message
gmail-to-sqlite sync-message --message-id MESSAGE_ID

# Detect and mark deleted messages only
gmail-to-sqlite sync-deleted-messages

# Use custom number of worker threads
gmail-to-sqlite sync --workers 8

# Ask natural language questions about your emails (single question mode)
gmail-to-sqlite chat --question "Who sent me the most emails?"

# Ask with custom result limit (single question mode)
gmail-to-sqlite chat --question "Show me unread emails from last week" --max-rows 10

# Start interactive chat session
gmail-to-sqlite chat
```

If you're using the development setup:

```bash
# Use python -m gmail_to_sqlite instead of gmail-to-sqlite
python -m gmail_to_sqlite sync
python -m gmail_to_sqlite chat
```

### Command Line Arguments

- `command`: Required. One of `sync`, `sync-message`, `sync-deleted-messages`, or `chat`
- `--full-sync`: Optional. Forces a complete sync of all messages
- `--message-id`: Required for `sync-message`. The ID of a specific message to sync
- `--question`: Optional for `chat`. Natural language question about your emails (if provided, asks question and exits; if not provided, starts interactive chat)
- `--max-rows`: Optional. Maximum number of rows to display in query results (default: 20)
- `--workers`: Optional. Number of worker threads (default: number of CPU cores)

**Note**: Data directory is configured in `.secrets.toml`, not via command line arguments.

### Graceful Shutdown

The application supports graceful shutdown when you press CTRL+C:

1. Stops accepting new tasks
2. Waits for currently running tasks to complete
3. Saves progress of completed work
4. Exits cleanly

Pressing CTRL+C a second time will force an immediate exit.

## Database Schema

The application creates a SQLite database with the following schema:

| Field        | Type     | Description                      |
| ------------ | -------- | -------------------------------- |
| message_id   | TEXT     | Unique Gmail message ID          |
| thread_id    | TEXT     | Gmail thread ID                  |
| sender       | JSON     | Sender information (name, email) |
| recipients   | JSON     | Recipients by type (to, cc, bcc) |
| labels       | JSON     | Array of Gmail labels            |
| subject      | TEXT     | Message subject                  |
| body         | TEXT     | Message body (plain text)        |
| size         | INTEGER  | Message size in bytes            |
| timestamp    | DATETIME | Message timestamp                |
| is_read      | BOOLEAN  | Read status                      |
| is_outgoing  | BOOLEAN  | Whether sent by user             |
| is_deleted   | BOOLEAN  | Whether deleted from Gmail       |
| last_indexed | DATETIME | Last sync timestamp              |

## AI-Powered Natural Language Queries

The `chat` command with the `--question` parameter allows you to ask single questions about your email database using natural language. Here are some example questions you can ask:

```bash
# Find your top email senders
gmail-to-sqlite chat --question "Who are the top 10 people who sent me emails?"

# Find emails about specific topics
gmail-to-sqlite chat --question "Show me emails about meetings from last month"

# Check unread emails
gmail-to-sqlite chat --question "How many unread emails do I have?"

# Find emails by size
gmail-to-sqlite chat --question "Show me the largest emails I've received"

# Time-based queries
gmail-to-sqlite chat --question "How many emails did I receive each day this week?"

# Find emails from specific domains
gmail-to-sqlite chat --question "Show me all emails from gmail.com addresses"
```

The AI agent will automatically convert your natural language question into a SQL query and execute it against your email database.

## Interactive Multi-Turn Chat

The `chat` command starts an interactive conversational interface powered by CrewAI agents. This allows for multi-turn conversations where the agent maintains context and can answer follow-up questions.

```bash
# Start interactive chat session
gmail-to-sqlite chat
```

Example conversation:

```
🤖 Agent ready! You can now chat about your Gmail data.

You: Who sends me the most emails?
🤖 Agent: I'll analyze your top email senders for you...

You: What about in the last month specifically?
🤖 Agent: Let me filter that to just the last month...

You: Can you show me some of those emails?
🤖 Agent: Here are some recent emails from your top senders...
```

Features of the interactive chat:

- **Context Preservation**: The agent remembers previous questions and responses
- **Natural Conversation**: Ask follow-up questions without repeating context
- **Smart Analysis**: CrewAI agents provide insights beyond simple SQL queries
- **Easy Exit**: Type `exit`, `quit`, or press Ctrl+C to end the session

## Manual SQL Queries

### Get the number of emails per sender

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Show the number of unread emails by sender

This is great to determine who is spamming you the most with uninteresting emails.

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE is_read = 0
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Get the number of emails for a specific period

- For years: `strftime('%Y', timestamp)`
- For months in a year: `strftime('%m', timestamp)`
- For days in a month: `strftime('%d', timestamp)`
- For weekdays: `strftime('%w', timestamp)`
- For hours in a day: `strftime('%H', timestamp)`

```sql
SELECT strftime('%Y', timestamp) AS period, COUNT(*) AS count
FROM messages
GROUP BY period
ORDER BY count DESC
```

### Find all newsletters and group them by sender

This is an amateurish way to find all newsletters and group them by sender. It's not perfect, but it's a start. You could also use

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE body LIKE '%newsletter%' OR body LIKE '%unsubscribe%'
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Show who has sent the largest emails in MB

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 AS size
FROM messages
GROUP BY sender->>'$.email'
ORDER BY size DESC
```

### Count the number of emails that I have sent to myself

```sql
SELECT count(*)
FROM messages
WHERE EXISTS (
  SELECT 1
  FROM json_each(messages.recipients->'$.to')
  WHERE json_extract(value, '$.email') = 'foo@example.com'
)
AND sender->>'$.email' = 'foo@example.com'
```

### List the senders who have sent me the largest total volume of emails in megabytes

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 as total_size
FROM messages
WHERE is_outgoing=false
GROUP BY sender->>'$.email'
ORDER BY total_size DESC
```

### Find all deleted messages

```sql
SELECT message_id, subject, timestamp
FROM messages
WHERE is_deleted=1
ORDER BY timestamp DESC
```
