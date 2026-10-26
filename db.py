"""
db.py
-----
Small helper file for talking to our SQLite database.

I kept this simple on purpose - just plain SQL queries using Python's
built-in sqlite3 module. No fancy ORM, just functions that open a
connection, run a query, and close the connection again.
"""

import sqlite3
import os

# Where the database file lives (same folder as this script)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datacenter.db")


def get_db():
    """Open a connection to the database and return it."""
    conn = sqlite3.connect(DB_PATH)
    # This makes rows behave like dictionaries, so we can do row["name"]
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create all the tables we need if they don't already exist,
    and add a default admin account so we can log in right away.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_code TEXT,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            os_name TEXT,
            server_type TEXT,
            location TEXT,
            port INTEGER,
            notes TEXT,
            status TEXT DEFAULT 'online',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Ensure missing columns exist if table was created previously
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(servers)").fetchall()]
    for col_name, col_type in [
        ("server_code", "TEXT"),
        ("os_name", "TEXT"),
        ("server_type", "TEXT"),
        ("location", "TEXT"),
        ("port", "INTEGER")
    ]:
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE servers ADD COLUMN {col_name} {col_type}")

    c.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpu_percent REAL,
            ram_percent REAL,
            disk_percent REAL,
            temperature REAL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT,
            message TEXT,
            severity TEXT,
            is_resolved INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            status TEXT DEFAULT 'Active',
            server_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE SET NULL
        )
    """)

    # Seed default Windows Server 2022 if not exists
    win_server = c.execute("SELECT id FROM servers WHERE name = 'DC-WIN-01'").fetchone()
    if not win_server:
        c.execute("""
            INSERT INTO servers (server_code, name, ip_address, os_name, server_type, location, port, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "SRV-001",
            "DC-WIN-01",
            "192.168.1.10",
            "Windows Server 2022",
            "Application Server",
            "Data Center Rack A1",
            3389,
            "online",
            "Pre-configured Windows Server 2022"
        ))
        win_id = c.lastrowid
    else:
        win_id = win_server["id"]

    # Seed assigned users for DC-WIN-01
    win_users_cnt = c.execute("SELECT COUNT(*) c FROM app_users WHERE server_id = ?", (win_id,)).fetchone()["c"]
    if win_users_cnt == 0:
        win_users = [
            ("Administrator", "admin@dc-win-01.local", "Active"),
            ("IT Manager", "itmanager@dc-win-01.local", "Active"),
        ]
        for u_name, u_email, u_status in win_users:
            c.execute(
                "INSERT INTO app_users (name, email, status, server_id) VALUES (?, ?, ?, ?)",
                (u_name, u_email, u_status, win_id)
            )

    # Seed default Ubuntu Server 22.04 LTS if not exists
    ubu_server = c.execute("SELECT id FROM servers WHERE name = 'DC-UBU-01'").fetchone()
    if not ubu_server:
        c.execute("""
            INSERT INTO servers (server_code, name, ip_address, os_name, server_type, location, port, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "SRV-002",
            "DC-UBU-01",
            "192.168.1.20",
            "Ubuntu Server 22.04 LTS",
            "Web Server",
            "Data Center Rack A2",
            22,
            "online",
            "Pre-configured Ubuntu Web Server"
        ))
        ubu_id = c.lastrowid
    else:
        ubu_id = ubu_server["id"]

    # Seed assigned users for DC-UBU-01
    ubu_users_cnt = c.execute("SELECT COUNT(*) c FROM app_users WHERE server_id = ?", (ubu_id,)).fetchone()["c"]
    if ubu_users_cnt == 0:
        ubu_users = [
            ("Web Administrator", "webadmin@dc-ubu-01.local", "Active"),
            ("DevOps Engineer", "devops@dc-ubu-01.local", "Active"),
        ]
        for u_name, u_email, u_status in ubu_users:
            c.execute(
                "INSERT INTO app_users (name, email, status, server_id) VALUES (?, ?, ?, ?)",
                (u_name, u_email, u_status, ubu_id)
            )

    # Create a default admin user if one doesn't exist yet
    existing = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        from werkzeug.security import generate_password_hash
        c.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123"))
        )

    conn.commit()
    conn.close()


def add_log(action, description):
    """Save one row into the activity log table."""
    conn = get_db()
    conn.execute(
        "INSERT INTO logs (action, description) VALUES (?, ?)",
        (action, description)
    )
    conn.commit()
    conn.close()
