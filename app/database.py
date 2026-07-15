import os
import time
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from app.logger import get_logger
from app.metrics import log_database_event

load_dotenv()
logger = get_logger(__name__)

def _extract_table_name(query: str) -> str:
    """Extract table name from SQL query for logging."""
    query_upper = query.upper().strip()
    if "FROM" in query_upper:
        parts = query_upper.split("FROM")
        if len(parts) > 1:
            return parts[1].strip().split()[0].lower()
    if "INTO" in query_upper:
        parts = query_upper.split("INTO")
        if len(parts) > 1:
            return parts[1].strip().split()[0].lower()
    if "UPDATE" in query_upper:
        parts = query_upper.split("UPDATE")
        if len(parts) > 1:
            return parts[1].strip().split()[0].lower()
    return "unknown"

def get_db_connection():
    """
    Creates and returns a PostgreSQL database connection.
    Uses the DATABASE_URL from .env file.
    """
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.autocommit = False
        logger.info("Database connection established")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def execute_query(query: str, params: tuple | None = None) -> list:
    start = time.time()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        results = cursor.fetchall()
        results = [dict(row) for row in results]
        duration = (time.time() - start) * 1000
        table = _extract_table_name(query)
        logger.info(f"Query executed successfully | rows={len(results)}")
        log_database_event("SELECT", table, duration, len(results), True)
        return results
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_database_event("SELECT", "unknown", duration, 0, False, str(e))
        logger.error(f"Query failed: {e} | query={query}")
        raise
    finally:
        if conn:
            conn.close()

def execute_write(query: str, params: tuple | None = None) -> bool:
    start = time.time()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        duration = (time.time() - start) * 1000
        table = _extract_table_name(query)
        logger.info("Write query executed successfully")
        log_database_event("WRITE", table, duration, 0, True)
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        duration = (time.time() - start) * 1000
        log_database_event("WRITE", "unknown", duration, 0, False, str(e))
        logger.error(f"Write query failed: {e}")
        raise
    finally:
        if conn:
            conn.close()
# ── Database query functions used by agent tools ──────────────────

def get_customer_by_name(customer_name: str) -> dict | None:
    """Get customer by name or email."""
    results = execute_query(
        """SELECT c.*, 
           COUNT(i.id) as total_issues
           FROM customers c
           LEFT JOIN issues i ON c.id = i.customer_id
           WHERE LOWER(c.name) = LOWER(%s) 
           OR LOWER(c.email) = LOWER(%s)
           GROUP BY c.id""",
        (customer_name, customer_name)
    )
    return results[0] if results else None

def get_open_issues(customer_id: int) -> list:
    """Get all open issues for a customer."""
    return execute_query(
        """
        SELECT i.*, c.name as customer_name 
        FROM issues i
        JOIN customers c ON i.customer_id = c.id
        WHERE i.customer_id = %s AND i.status = 'open'
        ORDER BY 
            CASE i.priority 
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 4
            END
        """,
        (customer_id,)
    )

def get_issue_history(issue_id: int) -> list:
    """Get all updates for a specific issue."""
    return execute_query(
        """
        SELECT iu.*, i.title as issue_title
        FROM issue_updates iu
        JOIN issues i ON iu.issue_id = i.id
        WHERE iu.issue_id = %s
        ORDER BY iu.created_at ASC
        """,
        (issue_id,)
    )

def get_next_actions(issue_id: int) -> list:
    """Get existing next actions for an issue."""
    return execute_query(
        "SELECT * FROM next_actions WHERE issue_id = %s",
        (issue_id,)
    )

def create_next_action(
    issue_id: int,
    action_text: str,
    assigned_to: str,
    due_date: str
) -> bool:
    """Create a new next action for an issue. Admin only."""
    return execute_write(
        """
        INSERT INTO next_actions 
        (issue_id, action_text, assigned_to, due_date, status)
        VALUES (%s, %s, %s, %s, 'pending')
        """,
        (issue_id, action_text, assigned_to, due_date)
    )

def update_issue_status(issue_id: int, status: str) -> bool:
    """Update issue status. Support user and admin only."""
    return execute_write(
        """
        UPDATE issues 
        SET status = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (status, issue_id)
    )