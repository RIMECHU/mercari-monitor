"""
Mercari日本 搜索爬虫 — 三级降级策略
"""
import logging
import time

logger = logging.getLogger(__name__)


def search_mercari(keyword, max_results=10, proxy=None):
    """
    搜索 Mercari 日本站点
    三级降级: mercapi → mercari库 → 内部API直连

    返回: list[dict] — [{"item_id", "name", "price", "url", "image_url"}, ...]
    """
    logger.info(f"搜索关键词: '{keyword}'")

    # Tier 1: mercapi 库（处理DPoP签名）
    try:
        return _search_via_mercapi(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 1 (mercapi) 失败: {e}")

    # Tier 2: mercari 库（marvinody版本）
    try:
        return _search_via_mercari_lib(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 2 (mercari库) 失败: {e}")

    # Tier 3: 直接API请求
    try:
        return _search_via_api(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 3 (API直连) 失败: {e}")

    logger.error(f"所有搜索策略均失败，关键词: '{keyword}'")
    return []


def _search_via_mercapi(keyword, max_results, proxy):
    """Tier 1: 使用 mercapi 库"""
    from mercapi import Mercapi
    import asyncio

    async def _search():
        m = Mercapi()
        results = await m.search(keyword)
        items = []
        count = 0
        async for item in results:
            if count >= max_results:
                break
            items.append({
                "item_id": str(item.id),
                "name": item.name,
                "price": item.price,
                "url": f"https://jp.mercari.com/item/{item.id}",
                "image_url": item.thumbnails[0] if item.thumbnails else "",
            })
            count += 1
        return items

    return asyncio.run(_search())


def _search_via_mercari_lib(keyword, max_results, proxy):
    """Tier 2: 使用 mercari 库 (marvinody/mercari)"""
    import mercari

    items = []
    count = 0
    for item in mercari.search(keyword):
        if count >= max_results:
            break
        items.append({
            "item_id": str(item.id),
            "name": item.productName if hasattr(item, 'productName') else str(item.name),
            "price": item.price,
            "url": item.productURL if hasattr(item, 'productURL') else f"https://jp.mercari.com/item/{item.id}",
            "image_url": item.imageURL if hasattr(item, 'imageURL') else "",
        })
        count += 1
        time.sleep(0.5)
    return items


def _search_via_api(keyword, max_results, proxy):
    """Tier 3: 使用 httpx 直接调用 Mercari 内部搜索 API"""
    import httpx
    import json

    # Mercari Japan 内部搜索 API
    search_url = "https://api.mercari.jp/v2/entities:search"

    headers = {
        "Accept": "application/json",
        "Accept-Language": "ja-JP,ja;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Content-Type": "application/json",
        "Origin": "https://jp.mercari.com",
        "Referer": "https://jp.mercari.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "X-Platform": "web",
    }

    # Mercari搜索请求体
    payload = {
        "userId": "",
        "pageSize": max_results,
        "pageToken": "",
        "searchSessionId": "",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "searchCondition": {
            "keyword": keyword,
            "excludeKeyword": "",
            "sort": "SORT_SCORE",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
            "sizeId": 0,
            "categoryId": 0,
            "brandId": 0,
            "sellerId": 0,
            "priceMin": 0,
            "priceMax": 0,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
        },
        "defaultSearchCondition": {
            "keyword": keyword,
            "sort": "SORT_SCORE",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
        },
        "serviceFrom": "web",
    }

    client_kwargs = {"timeout": 15}
    if proxy:
        client_kwargs["proxy"] = proxy

    with httpx.Client(**client_kwargs) as client:
        resp = client.post(search_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    items = []
    for result in data.get("items", []):
        item_id = result.get("id", "")
        items.append({
            "item_id": str(item_id),
            "name": result.get("name", "Unknown"),
            "price": result.get("price", 0),
            "url": f"https://jp.mercari.com/item/{item_id}",
            "image_url": (result.get("thumbnails", [""]) or [""])[0] if result.get("thumbnails") else "",
        })

    return items


# 便捷别名
def search(keyword, max_results=10, proxy=None):
    """search_mercari 的短别名"""
    return search_mercari(keyword, max_results, proxy)
