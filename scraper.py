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
    # 自动补全代理URL的scheme
    if proxy and "://" not in proxy:
        proxy = "http://" + proxy

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
    """Tier 3: 使用 Playwright 浏览器渲染 Mercari 搜索页面"""
    from playwright.sync_api import sync_playwright
    import re as _re

    encoded_keyword = keyword.replace(" ", "+")
    search_url = f"https://jp.mercari.com/search?keyword={encoded_keyword}&status=on_sale"

    items = []
    with sync_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        }
        try:
            browser = p.chromium.launch(channel="chrome", **launch_args)
        except Exception:
            browser = p.chromium.launch(**launch_args)

        context_args = {
            "locale": "ja-JP",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        }
        if proxy:
            context_args["proxy"] = {"server": proxy}

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # 等待骨架屏消失（搜索API返回数据）
            try:
                page.wait_for_selector(
                    "li[data-testid='item-cell-skeleton']",
                    state="detached",
                    timeout=20000,
                )
            except Exception:
                page.wait_for_timeout(10000)

            # 从渲染后的HTML中提取商品链接
            html = page.content()
            links = _re.findall(r'href="(/item/m\d+)"', html)
            seen_ids = set()

            for link in links:
                if len(items) >= max_results:
                    break

                item_id = link.split("/item/")[-1]
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                full_url = f"https://jp.mercari.com{link}"

                # 尝试从DOM获取名称和价格
                try:
                    name_el = page.query_selector(f"a[href='{link}']")
                    if name_el:
                        parent_text = name_el.evaluate("""el => {
                            let p = el.closest('li');
                            return p ? p.innerText : '';
                        }""")
                        lines = [l.strip() for l in parent_text.split("\n") if l.strip()]
                        # 寻找最长的文本行作为名称（价格行通常较短）
                        name = ""
                        price = 0
                        for line in lines:
                            digit_match = _re.search(r'(\d[\d,]*)', line)
                            if digit_match and len(line.replace(",", "").replace(" ", "")) < 18:
                                # 短行+数字 = 价格行
                                p = int(digit_match.group(1).replace(",", ""))
                                if p > price and p < 99999999:
                                    price = p
                            elif len(line) > len(name) and "\\xa5" not in line:
                                name = line
                        items.append({
                            "item_id": item_id,
                            "name": name or f"Mercari {item_id}",
                            "price": price,
                            "url": full_url,
                            "image_url": "",
                        })
                except Exception:
                    # 即使无法获取名称/价格，也添加链接
                    items.append({
                        "item_id": item_id,
                        "name": f"Mercari {item_id}",
                        "price": 0,
                        "url": full_url,
                        "image_url": "",
                    })

        except Exception as e:
            logger.error(f"Playwright搜索出错: {e}")

        browser.close()

    return items


# 便捷别名
def search(keyword, max_results=10, proxy=None):
    """search_mercari 的短别名"""
    return search_mercari(keyword, max_results, proxy)
