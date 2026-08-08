CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL CHECK(category IN ('office','personal','side-hustle','shopping','learning')),
    title TEXT NOT NULL,
    notes TEXT,
    priority TEXT CHECK(priority IN ('low','medium','high')) DEFAULT 'medium',
    due_date TEXT,
    recurrence_rule TEXT,
    status TEXT CHECK(status IN ('open','in_progress','done')) DEFAULT 'open',
    reminder_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    source_date TEXT,
    tags TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title, content, content='knowledge', content_rowid='id'
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id INTEGER PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
