import sqlite3

DB_NAME = "brain_memory.db"

def init_db():
    """Initializes the SQLite schema for the Gen-3 factory."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table 1: The surviving alpha population
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alpha_population (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT UNIQUE,
            alpha_id TEXT,
            generation INTEGER,
            sharpe REAL,
            turnover REAL,
            fitness REAL,
            ast_depth INTEGER,
            is_tuned BOOLEAN DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table 2: Vector memory for fast TF-IDF deduplication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vector_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT UNIQUE,
            vector_blob TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def save_alpha(expression, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned=0):
    """Logs an evaluated alpha to the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO alpha_population (expression, alpha_id, generation, sharpe, turnover, fitness, ast_depth, is_tuned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (expression, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Ignore duplicates
    finally:
        conn.close()

def get_top_population(limit=150):
    """Retrieves the strongest alphas for the next generation's crossover."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT expression, sharpe, turnover, ast_depth 
        FROM alpha_population 
        WHERE sharpe > 0.5 AND turnover < 0.8
        ORDER BY sharpe DESC LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results
