"""
数据库初始化模块
"""
import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(__file__), 'mercari_monitor.db')


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword       TEXT    NOT NULL,
            target_price  INTEGER NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            active        INTEGER NOT NULL DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            item_id     TEXT    NOT NULL,
            item_name   TEXT    NOT NULL,
            item_price  INTEGER NOT NULL,
            item_url    TEXT    NOT NULL,
            image_url   TEXT    DEFAULT '',
            scraped_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            notified    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    ''')

    # 索引
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_product
        ON price_history(product_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_item
        ON price_history(item_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_history_scraped
        ON price_history(scraped_at)
    ''')

    conn.commit()
    conn.close()
