"""
定时检查任务 — 搜索所有活跃商品并发送提醒
"""
import time
import logging
from datetime import datetime

from models import get_all_products, add_price_record, has_been_notified, mark_notified
from scraper import search_mercari, close_shared_browser
from digimart_scraper import search_digimart
from notifier import send_price_alert
from config import get_effective_sendkey, load_config

logger = logging.getLogger(__name__)


def _search_source(source, keyword, max_results, proxy):
    """根据source选择合适的爬虫"""
    if source == 'digimart':
        return search_digimart(keyword, max_results, proxy)
    else:
        return search_mercari(keyword, max_results, proxy)


def check_all_active_products():
    """
    检查所有活跃商品:
      1. 搜索每个关键词
      2. 保存价格记录
      3. 低于目标价且未推送 → 发送微信提醒
    """
    config = load_config()
    sendkey = get_effective_sendkey()
    notification_enabled = config.get("notification_enabled", True)
    max_results = config.get("max_results_per_search", 10)
    proxy = config.get("proxy", "") or None

    if notification_enabled and not sendkey:
        logger.warning("Server酱 SendKey 未配置，跳过通知")

    products = get_all_products()
    active_products = [p for p in products if p["active"]]

    if not active_products:
        logger.info("没有活跃的监控商品")
        return

    logger.info(f"开始检查 {len(active_products)} 个活跃商品...")
    total_found = 0
    total_alerts = 0

    for product in active_products:
        pid = product["id"]
        keyword = product["keyword"]
        target_price = product["target_price"]
        source = product.get("source", "mercari")

        logger.info(f"  [{pid}] 搜索[{source}]: {keyword}")

        try:
            items = _search_source(source, keyword, max_results, proxy)
        except Exception as e:
            logger.error(f"  [{pid}] 搜索失败: {e}")
            continue

        if not items:
            logger.info(f"  [{pid}] 未找到结果")
            continue

        total_found += len(items)

        # 过滤：只保留名称中包含关键词的商品
        keyword_parts = [k.lower() for k in keyword.split() if len(k) >= 2]
        filtered_items = []
        for item in items:
            item_name_lower = item["name"].lower()
            # 所有关键词片段都必须出现在商品名中
            if all(part in item_name_lower for part in keyword_parts):
                filtered_items.append(item)
            else:
                logger.debug(f"  过滤: '{item['name'][:40]}' 不包含所有关键词")

        logger.info(f"  [{pid}] 搜索到 {len(items)} 个, 关键词匹配 {len(filtered_items)} 个")

        for item in filtered_items:
            # 保存价格记录
            record_id = add_price_record(
                pid,
                item["item_id"],
                item["name"],
                item["price"],
                item["url"],
                item.get("image_url", "")
            )

            # 检查是否低于目标价
            if item["price"] <= target_price and record_id:
                # 检查是否已经推送过
                if not has_been_notified(pid, item["item_id"]):
                    logger.info(f"  [{pid}] 🔔 触发提醒: {item['name']} ¥{item['price']} (目标: ¥{target_price})")
                    if notification_enabled and sendkey:
                        success = send_price_alert(
                            sendkey, keyword, target_price,
                            item["name"], item["price"], item["url"],
                            item.get("image_url", "")
                        )
                        if success:
                            mark_notified(record_id)
                            total_alerts += 1
                    else:
                        # 未配置通知也标记，避免后续重复提醒
                        mark_notified(record_id)
                        total_alerts += 1

        # 商品之间休息3秒，防止被Mercari限流
        time.sleep(3)

    # 关闭共享浏览器释放内存
    close_shared_browser()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"检查完成 ({now}): 找到 {total_found} 个商品, 发送 {total_alerts} 条提醒")
    return {"found": total_found, "alerts": total_alerts, "checked_at": now}


def check_single_product(product_id):
    """手动检查单个商品"""
    from models import get_product

    product = get_product(product_id)
    if not product:
        return {"error": "商品不存在"}, 404

    config = load_config()
    sendkey = get_effective_sendkey()
    notification_enabled = config.get("notification_enabled", True)
    max_results = config.get("max_results_per_search", 10)
    proxy = config.get("proxy", "") or None

    source = product.get("source", "mercari")
    items = _search_source(source, product["keyword"], max_results, proxy)

    # 过滤：只保留名称中包含关键词的商品
    keyword = product["keyword"]
    keyword_parts = [k.lower() for k in keyword.split() if len(k) >= 2]
    filtered_items = [i for i in items if all(p in i["name"].lower() for p in keyword_parts)]

    found = 0
    alerts = 0

    for item in filtered_items:
        record_id = add_price_record(
            product_id,
            item["item_id"],
            item["name"],
            item["price"],
            item["url"],
            item.get("image_url", "")
        )

        if record_id:
            found += 1

        if item["price"] <= product["target_price"] and record_id:
            if not has_been_notified(product_id, item["item_id"]):
                if notification_enabled and sendkey:
                    if send_price_alert(
                        sendkey, product["keyword"], product["target_price"],
                        item["name"], item["price"], item["url"],
                        item.get("image_url", "")
                    ):
                        mark_notified(record_id)
                        alerts += 1
                else:
                    mark_notified(record_id)
                    alerts += 1

    return {"found": found, "alerts": alerts}
