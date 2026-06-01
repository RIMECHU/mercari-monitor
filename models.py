"""
数据库CRUD操作
"""
from db import get_db


# ── 商品(product)操作 ──

def add_product(keyword, target_price):
    """添加监控商品，返回新ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (keyword, target_price) VALUES (?, ?)",
        (keyword.strip(), int(target_price))
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_all_products():
    """获取所有商品，附带最新价格摘要"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            p.id, p.keyword, p.target_price, p.active, p.created_at,
            (SELECT MAX(scraped_at) FROM price_history WHERE product_id = p.id) AS last_checked_at,
            (SELECT item_price FROM price_history
             WHERE product_id = p.id
             ORDER BY item_price ASC LIMIT 1) AS lowest_price_found,
            (SELECT item_url FROM price_history
             WHERE product_id = p.id
             ORDER BY item_price ASC LIMIT 1) AS lowest_item_url,
            (SELECT COUNT(*) FROM price_history
             WHERE product_id = p.id AND notified = 1) AS total_alerts
        FROM products p
        ORDER BY p.created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_product(product_id):
    """获取单个商品"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_product(product_id):
    """删除商品及其价格历史(CASCADE)"""
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()


def toggle_product(product_id):
    """切换商品激活状态，返回新状态；商品不存在返回None"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE products SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
        (product_id,)
    )
    conn.commit()
    cursor.execute("SELECT active FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row['active']) if row else None


# ── 价格历史(price_history)操作 ──

def add_price_record(product_id, item_id, item_name, item_price, item_url, image_url=''):
    """添加一条价格记录，返回记录ID；如果同一商品在同一次检查中已存在则跳过，返回None"""
    conn = get_db()
    cursor = conn.cursor()

    # 检查是否在最近一次检查中已经记录过同一item
    cursor.execute('''
        SELECT id FROM price_history
        WHERE product_id = ? AND item_id = ?
        AND scraped_at > datetime('now', 'localtime', '-5 minutes')
    ''', (product_id, item_id))

    if cursor.fetchone():
        conn.close()
        return None

    cursor.execute(
        "INSERT INTO price_history (product_id, item_id, item_name, item_price, item_url, image_url) VALUES (?, ?, ?, ?, ?, ?)",
        (product_id, str(item_id), item_name, int(item_price), item_url, image_url)
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id


def get_price_history(product_id, limit=50):
    """获取某商品的价格历史"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM price_history WHERE product_id = ? ORDER BY scraped_at DESC LIMIT ?",
        (product_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def has_been_notified(product_id, item_id):
    """检查某商品-某item是否已经推送过"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM price_history WHERE product_id = ? AND item_id = ? AND notified = 1",
        (product_id, str(item_id))
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_notified(record_id):
    """标记价格记录为已推送"""
    conn = get_db()
    conn.execute("UPDATE price_history SET notified = 1 WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


# ── 统计操作 ──

def get_stats():
    """获取仪表盘统计信息"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM products WHERE active = 1")
    active_count = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) AS count FROM price_history WHERE notified = 1")
    total_alerts = cursor.fetchone()['count']

    cursor.execute("SELECT MAX(scraped_at) AS last_check FROM price_history")
    last_check = cursor.fetchone()['last_check']

    conn.close()
    return {
        "active_products": active_count,
        "total_alerts_sent": total_alerts,
        "last_check_at": last_check,
    }
