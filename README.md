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

#### Option 1: Global Installation with pipx (Recommended)

```bash
# Install from source with pipx (package not yet on PyPI)
git clone https://github.com/marcboeker/gmail-to-sqlite.git
cd gmail-to-sqlite
pipx install .
```

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

2. **Set up OpenAI API key (for AI features):**
   - Get an API key from [OpenAI](https://platform.openai.com/api-keys)
   - Set environment variable: `export OPENAI_API_KEY=your-openai-api-key-here`
   - Or create a `.env` file in your data directory with `OPENAI_API_KEY=your-openai-api-key-here`

## Usage

### Configuration

You can configure the application in two ways:

1. **Environment Variables**: Create a `.env` file (copy from `.env.example`)
2. **Command Line Arguments**: Use command-line flags like `--data-dir`

```bash
# Copy the example configuration
cp .env.example .env

# Edit .env to set your data directory and OpenAI API key
# GMAIL_DATA_DIR=./data
# OPENAI_API_KEY=your-openai-api-key-here
```

### Basic Commands

If you installed with pipx (Option 1):

```bash
# Incremental sync (default) - using environment variable
gmail-to-sqlite sync

# Incremental sync with command line argument
gmail-to-sqlite sync --data-dir ./data

# Full sync with deletion detection
gmail-to-sqlite sync --data-dir ./data --full-sync

# Sync a specific message
gmail-to-sqlite sync-message --data-dir ./data --message-id MESSAGE_ID

# Detect and mark deleted messages only
gmail-to-sqlite sync-deleted-messages --data-dir ./data

# Use custom number of worker threads
gmail-to-sqlite sync --data-dir ./data --workers 8

# Ask natural language questions about your emails (single question mode)
gmail-to-sqlite chat --data-dir ./data --question "Who sent me the most emails?"

# Ask with custom result limit (single question mode)
gmail-to-sqlite chat --data-dir ./data --question "Show me unread emails from last week" --max-rows 10

# Start interactive chat session
gmail-to-sqlite chat --data-dir ./data
```

If you're using the development setup (Option 2):

```bash
# Use python -m gmail_to_sqlite instead of gmail-to-sqlite
python -m gmail_to_sqlite sync --data-dir ./data
python -m gmail_to_sqlite chat --data-dir ./data
```

### Command Line Arguments

- `command`: Required. One of `sync`, `sync-message`, `sync-deleted-messages`, or `chat`
- `--data-dir`: Optional. Directory where the SQLite database will be stored (can also be set via `GMAIL_DATA_DIR` environment variable)
- `--full-sync`: Optional. Forces a complete sync of all messages
- `--message-id`: Required for `sync-message`. The ID of a specific message to sync
- `--question`: Optional for `chat`. Natural language question about your emails (if provided, asks question and exits; if not provided, starts interactive chat)
- `--max-rows`: Optional. Maximum number of rows to display in query results (default: 20)
- `--workers`: Optional. Number of worker threads (default: number of CPU cores)

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
gmail-to-sqlite chat --data-dir ./data --question "Who are the top 10 people who sent me emails?"

# Find emails about specific topics
gmail-to-sqlite chat --data-dir ./data --question "Show me emails about meetings from last month"

# Check unread emails
gmail-to-sqlite chat --data-dir ./data --question "How many unread emails do I have?"

# Find emails by size
gmail-to-sqlite chat --data-dir ./data --question "Show me the largest emails I've received"

# Time-based queries
gmail-to-sqlite chat --data-dir ./data --question "How many emails did I receive each day this week?"

# Find emails from specific domains
gmail-to-sqlite chat --data-dir ./data --question "Show me all emails from gmail.com addresses"
```

The AI agent will automatically convert your natural language question into a SQL query and execute it against your email database.

## Interactive Multi-Turn Chat

The `chat` command starts an interactive conversational interface powered by CrewAI agents. This allows for multi-turn conversations where the agent maintains context and can answer follow-up questions.

```bash
# Start interactive chat session
gmail-to-sqlite chat --data-dir ./data
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
