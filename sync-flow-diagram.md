# Gmail-to-SQLite Sync Flow

```mermaid
flowchart TD
    A[Start Sync] --> B[Initialize Service & Labels]
    B --> C{Full Sync?}

    C -->|No| D[Get last_indexed timestamp]
    C -->|Yes| E[No Query Filters]

    D --> G[Build Query: after:last_indexed]

    E --> H[Get All Message IDs from Gmail]
    G --> H

    H --> I[Check for Deleted Messages]
    I --> J[Create Thread Pool]

    J --> K[For Each Message ID]
    K --> L[Fetch Message from Gmail API]
    L --> M{Message Exists in DB?}

    M -->|No| N[Parse & Store Message]
    M -->|Yes| O[Skip - Already Synced]

    N --> P[Update last_indexed timestamp]
    O --> Q[Continue to Next Message]
    P --> Q

    Q --> R{More Messages?}
    R -->|Yes| K
    R -->|No| S[Sync Complete]

    S --> T[Log Results]

    subgraph "Key Functions"
        U[last_indexed] --> U1[Returns msg.last_indexed<br/>NOT msg.timestamp]
    end

    subgraph "Database Schema"
        W[Message Table]
        W --> X[message_id: TEXT]
        W --> Y[timestamp: DATETIME<br/>Original message date]
        W --> Z[last_indexed: DATETIME<br/>When synced to DB]
    end

    subgraph "The Bugs & Fixes"
        AA[BUG 1: Functions returned msg.timestamp]
        AA --> BB[Caused wrong date ranges]

        CC[BUG 2: Query used OR logic]
        CC --> DD[Got messages after X OR before Y]
        DD --> EE[Matched almost everything]

        FF[FIX 1: Use msg.last_indexed]
        GG[FIX 2: Only query after last sync]
        FF --> HH[Correct timestamps for ranges]
        GG --> II[Only get new messages]
    end

    style N fill:#90EE90
    style U1 fill:#FFB6C1
    style FF fill:#90EE90
    style GG fill:#90EE90
    style HH fill:#90EE90
    style II fill:#90EE90
```

## Sync Process Explanation

1. **Initialization**: Create Gmail service and fetch labels
2. **Query Building**:
   - For incremental sync: Use `last_indexed()` and `first_indexed()` to create date range
   - For full sync: No date filters
3. **Message Collection**: Get all message IDs matching the query from Gmail
4. **Deletion Detection**: Compare Gmail IDs with DB IDs to mark deleted messages
5. **Parallel Processing**: Use thread pool to fetch and process messages
6. **Storage**: Parse and store new messages, skip existing ones

## The Bugs That Were Fixed

**Bug 1: Wrong Timestamp Source**

- `last_indexed()` and `first_indexed()` returned `msg.timestamp` (original message date) instead of `msg.last_indexed` (sync date)
- Caused incorrect date ranges in Gmail queries

**Bug 2: OR Logic in Query**

- Gmail query used `" | ".join(query)` creating `after:X | before:Y` (OR logic)
- This matched messages "after recent date OR before old date" = almost everything
- Caused full re-sync every time

## The Solution

**Fix 1:** Changed functions to return `msg.last_indexed`
**Fix 2:** Removed `first_indexed()` and OR logic - only query `after:last_indexed`

Result: Incremental sync now only fetches truly new messages!
