#!/usr/bin/env python3
"""Migration script to create API key tables."""

import logging
from pathlib import Path

from src.database.connection import DatabaseConnection


# SQL for creating tables (compatible with both PostgreSQL and SQLite)
CREATE_API_KEYS_TABLE = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    last_used_at TEXT,
    is_active INTEGER DEFAULT 1,
    rate_limit_per_hour INTEGER DEFAULT 1000,
    allowed_ips TEXT,
    environment TEXT DEFAULT 'production'
)
"""

CREATE_API_KEY_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS api_key_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    response_time_ms INTEGER,
    status_code INTEGER,
    FOREIGN KEY (api_key_id) REFERENCES api_keys(key_id) ON DELETE CASCADE
)
"""

# Create indexes
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys(key_hash)",
    "CREATE INDEX IF NOT EXISTS idx_user_id ON api_keys(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_is_active ON api_keys(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_expires_at ON api_keys(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_api_key_id ON api_key_usage(api_key_id)",
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON api_key_usage(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_endpoint ON api_key_usage(endpoint)",
]


def run_migration():
    """Run the migration to create API key tables."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting API key tables migration...")
    
    # Initialize database connection
    db = DatabaseConnection()
    
    try:
        # Start transaction
        db.begin_transaction()
        
        # Create api_keys table
        logger.info("Creating api_keys table...")
        db.execute_update(CREATE_API_KEYS_TABLE, {})
        
        # Create api_key_usage table
        logger.info("Creating api_key_usage table...")
        db.execute_update(CREATE_API_KEY_USAGE_TABLE, {})
        
        # Create indexes
        logger.info("Creating indexes...")
        for index_sql in CREATE_INDEXES:
            db.execute_update(index_sql, {})
        
        # Commit transaction
        db.commit_transaction()
        
        logger.info("Migration completed successfully!")
        
        # Verify tables were created
        tables = db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('api_keys', 'api_key_usage')",
            {}
        )
        
        if len(tables) == 2:
            logger.info("✓ Both tables created successfully")
        else:
            logger.warning(f"Expected 2 tables, found {len(tables)}")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        db.rollback_transaction()
        raise
    
    finally:
        # Clean up
        if hasattr(db, 'close'):
            db.close()


def rollback_migration():
    """Rollback the migration (drop tables)."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Rolling back API key tables migration...")
    
    # Initialize database connection
    db = DatabaseConnection()
    
    try:
        # Start transaction
        db.begin_transaction()
        
        # Drop tables
        logger.info("Dropping api_key_usage table...")
        db.execute_update("DROP TABLE IF EXISTS api_key_usage", {})
        
        logger.info("Dropping api_keys table...")
        db.execute_update("DROP TABLE IF EXISTS api_keys", {})
        
        # Commit transaction
        db.commit_transaction()
        
        logger.info("Rollback completed successfully!")
        
    except Exception as e:
        logger.error(f"Rollback failed: {str(e)}")
        db.rollback_transaction()
        raise
    
    finally:
        # Clean up
        if hasattr(db, 'close'):
            db.close()


def check_migration_status():
    """Check if migration has been run."""
    db = DatabaseConnection()
    
    try:
        tables = db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('api_keys', 'api_key_usage')",
            {}
        )
        
        if len(tables) == 2:
            print("✓ API key tables exist")
            
            # Check for data
            key_count = db.execute_query("SELECT COUNT(*) as count FROM api_keys", {})
            usage_count = db.execute_query("SELECT COUNT(*) as count FROM api_key_usage", {})
            
            print(f"  - API keys: {key_count[0]['count'] if key_count else 0}")
            print(f"  - Usage records: {usage_count[0]['count'] if usage_count else 0}")
        else:
            print("✗ API key tables do not exist")
            print(f"  Found tables: {[t['name'] for t in tables]}")
            
    except Exception as e:
        print(f"✗ Error checking migration status: {str(e)}")
    
    finally:
        if hasattr(db, 'close'):
            db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "up":
            run_migration()
        elif command == "down":
            rollback_migration()
        elif command == "status":
            check_migration_status()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python migrate_api_keys.py [up|down|status]")
            sys.exit(1)
    else:
        print("Usage: python migrate_api_keys.py [up|down|status]")
        print("  up     - Run the migration")
        print("  down   - Rollback the migration")
        print("  status - Check migration status")