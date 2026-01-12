PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    corrects_message_id INTEGER,
    FOREIGN KEY (corrects_message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    conversation_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, message_id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    conversation_id INTEGER,
    causality_message_id INTEGER,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (causality_message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS preference_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    proposal_text TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'dismissed')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    decided_at DATETIME,
    causality_message_id INTEGER,
    assistant_message_id INTEGER,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (causality_message_id) REFERENCES messages(id),
    FOREIGN KEY (assistant_message_id) REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_event_id INTEGER,
    source_proposal_id INTEGER,
    FOREIGN KEY (approved_event_id) REFERENCES events(id),
    FOREIGN KEY (source_proposal_id) REFERENCES preference_proposals(id)
);

CREATE TABLE IF NOT EXISTS preference_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL DEFAULT 'global',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reset_event_id INTEGER,
    FOREIGN KEY (reset_event_id) REFERENCES events(id)
);

CREATE TRIGGER IF NOT EXISTS prevent_update_messages
BEFORE UPDATE ON messages
BEGIN
    SELECT RAISE(ABORT, 'Messages are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_messages
BEFORE DELETE ON messages
BEGIN
    SELECT RAISE(ABORT, 'Messages are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_update_events
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'Events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_events
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'Events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_update_preferences
BEFORE UPDATE ON preferences
BEGIN
    SELECT RAISE(ABORT, 'Preferences are immutable; append new preferences instead');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_preferences
BEFORE DELETE ON preferences
BEGIN
    SELECT RAISE(ABORT, 'Preferences are immutable; append new preferences instead');
END;

CREATE TRIGGER IF NOT EXISTS prevent_update_preference_resets
BEFORE UPDATE ON preference_resets
BEGIN
    SELECT RAISE(ABORT, 'Preference resets are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_preference_resets
BEFORE DELETE ON preference_resets
BEGIN
    SELECT RAISE(ABORT, 'Preference resets are immutable');
END;
