#!/usr/bin/env python3
"""Test SQLite database connection"""

import sqlite3
import sys
import os

DB_NAME = "myapp.db"

try:
    # Check if database file exists
    if not os.path.exists(DB_NAME):
        print(f"Database file '{DB_NAME}' not found")
        sys.exit(1)
    
    # Connect to database and get version
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sqlite_version()")
    version = cursor.fetchone()[0]
    conn.close()
    
    print(f"SQLite version: {version}")
    sys.exit(0)
    
except sqlite3.Error as e:
    print(f"Connection failed: {e}")
    sys.exit(1)
