#!/usr/bin/env python3
"""Interactive SQLite database shell for notes_database"""

import sqlite3
import sys

DB_NAME = "myapp.db"

def print_help():
    """Print help information"""
    print("""
SQLite Interactive Shell Commands:
  .help                Show this help message
  .tables              List all tables
  .schema [table]      Show CREATE statements
  .describe [table]    Show table structure
  .quit or .exit       Exit the shell
  
Standard SQL commands are also supported (SELECT, INSERT, UPDATE, DELETE, etc.)
""")

def list_tables(cursor):
    """List all tables in the database"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = cursor.fetchall()
    if tables:
        print("Tables:")
        for table in tables:
            print(f"  {table[0]}")
    else:
        print("No tables found")

def show_schema(cursor, table_name=None):
    """Show CREATE statements for tables"""
    if table_name:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()
        if result:
            print(result[0])
        else:
            print(f"Table '{table_name}' not found")
    else:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        for row in cursor.fetchall():
            print(row[0])
            print()

def describe_table(cursor, table_name):
    """Show table structure"""
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        if columns:
            print(f"\nTable: {table_name}")
            print("-" * 80)
            print(f"{'Column':<20} {'Type':<15} {'Null':<6} {'Default':<15} {'Primary Key':<12}")
            print("-" * 80)
            for col in columns:
                print(f"{col[1]:<20} {col[2]:<15} {'YES' if col[3]==0 else 'NO':<6} {str(col[4] or ''):<15} {'YES' if col[5]==1 else 'NO':<12}")
        else:
            print(f"Table '{table_name}' not found")
    except sqlite3.Error as e:
        print(f"Error: {e}")

def execute_query(cursor, query):
    """Execute a SQL query and display results"""
    try:
        cursor.execute(query)
        
        # Check if this is a SELECT query
        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            if rows:
                # Get column names
                columns = [description[0] for description in cursor.description]
                
                # Calculate column widths
                widths = [len(col) for col in columns]
                for row in rows:
                    for i, val in enumerate(row):
                        widths[i] = max(widths[i], len(str(val)))
                
                # Print header
                header = " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
                print(header)
                print("-" * len(header))
                
                # Print rows
                for row in rows:
                    print(" | ".join(str(val).ljust(widths[i]) for i, val in enumerate(row)))
                
                print(f"\n{len(rows)} row(s) returned")
            else:
                print("No results returned")
        else:
            # For non-SELECT queries
            print(f"Query executed successfully. {cursor.rowcount} row(s) affected.")
            
    except sqlite3.Error as e:
        print(f"Error: {e}")

def main():
    """Main interactive shell loop"""
    print(f"SQLite Interactive Shell - Database: {DB_NAME}")
    print("Type .help for help, .quit to exit\n")
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        while True:
            try:
                # Get user input
                query = input("sqlite> ").strip()
                
                if not query:
                    continue
                    
                # Handle special commands
                if query.startswith("."):
                    cmd_parts = query.split()
                    cmd = cmd_parts[0].lower()
                    
                    if cmd in [".quit", ".exit"]:
                        break
                    elif cmd == ".help":
                        print_help()
                    elif cmd == ".tables":
                        list_tables(cursor)
                    elif cmd == ".schema":
                        table_name = cmd_parts[1] if len(cmd_parts) > 1 else None
                        show_schema(cursor, table_name)
                    elif cmd == ".describe":
                        if len(cmd_parts) > 1:
                            describe_table(cursor, cmd_parts[1])
                        else:
                            print("Usage: .describe [table_name]")
                    else:
                        print(f"Unknown command: {cmd}")
                        print("Type .help for help")
                else:
                    # Execute SQL query
                    execute_query(cursor, query)
                    
                    # Commit if it's a write operation
                    if any(query.upper().startswith(cmd) for cmd in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]):
                        conn.commit()
                        
            except KeyboardInterrupt:
                print("\nUse .quit to exit")
                continue
            except EOFError:
                break
                
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
        print("\nGoodbye!")

if __name__ == "__main__":
    main()
