"""
Mercari日本 搜索爬虫 — 三级降级策略，共享浏览器复用
"""
import logging
import time
import re as _re

logger = logging.getLogger(__name__)

# 实时汇率缓存
_usd_to_jpy_rate = 150



def _get_usd_jpy_rate():
    """获取实时 USD→JPY 汇率"""
    global _usd_to_jpy_rate
    try:
        import httpx as _httpx
        r = _httpx.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        if r.status_code == 200:
            _usd_to_jpy_rate = int(r.json()["rates"]["JPY"])
            logger.info(f"实时汇率: 1 USD = {_usd_to_jpy_rate} JPY")
    except Exception:
        pass
    return _usd_to_jpy_rate


def search_mercari(keyword, max_results=10, proxy=None):
    """搜索 Mercari 日本站点。proxy自动补全scheme"""
    if proxy and "://" not in proxy:
        proxy = "http://" + proxy
    logger.info(f"搜索关键词: '{keyword}'")

    # Tier 1: mercapi
    try:
        return _search_via_mercapi(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 1 (mercapi) 失败: {e}")

    # Tier 2: mercari
    try:
        return _search_via_mercari_lib(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 2 (mercari库) 失败: {e}")

    # Tier 3: Playwright 浏览器（复用共享实例）
    try:
        return _search_via_playwright(keyword, max_results, proxy)
    except Exception as e:
        logger.warning(f"Tier 3 (Playwright) 失败: {e}")

    return []


def _search_via_mercapi(keyword, max_results, proxy):
    """Tier 1: mercapi 库"""
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
                "item_id": str(item.id), "name": item.name, "price": item.price,
                "url": f"https://jp.mercari.com/item/{item.id}",
                "image_url": item.thumbnails[0] if item.thumbnails else "",
            })
            count += 1
        return items
    return asyncio.run(_search())


def _search_via_mercari_lib(keyword, max_results, proxy):
    """Tier 2: mercari 库"""
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


def _search_via_playwright(keyword, max_results, proxy):
    """Tier 3: Playwright 浏览器渲染"""
    from playwright.sync_api import sync_playwright

    search_url = "https://jp.mercari.com/search?keyword={}&status=on_sale".format(
        keyword.replace(" ", "+")
    )
    items = []

    with sync_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }
        try:
            browser = p.chromium.launch(channel="chrome", **launch_args)
        except Exception:
            browser = p.chromium.launch(**launch_args)

        context_args = {
            "locale": "ja-JP",
            "timezone_id": "Asia/Tokyo",
            "extra_http_headers": {"Accept-Language": "ja-JP,ja;q=0.9"},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
            ),
        }
        if proxy and proxy.startswith("http"):
            context_args["proxy"] = {"server": proxy}

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # 等待骨架屏消失（最多等15秒，超时加5秒）
            try:
                page.wait_for_selector(
                    "li[data-testid='item-cell-skeleton']",
                    state="detached",
                    timeout=15000,
                )
            except Exception:
                page.wait_for_timeout(5000)

            # 从HTML提取商品链接
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

                full_url = "https://jp.mercari.com" + link

                # 提取图片、名称、价格（精确class选择器）
                try:
                    name_el = page.query_selector("a[href='{}']".format(link))
                    if name_el:
                        info_json = name_el.evaluate("""el => {
                            let card = el.closest('li');
                            if (!card) return '{}';
                            let img = card.querySelector('img');
                            let imgSrc = img ? (img.src || '') : '';
                            let nameEl = card.querySelector('[class*="itemName"]');
                            let name = nameEl ? nameEl.innerText.trim() : '';
                            let curEl = card.querySelector('[class*="currency"]');
                            let numEl = card.querySelector('[class*="number"]');
                            let currency = curEl ? curEl.innerText.trim() : '';
                            let number = numEl ? numEl.innerText.trim() : '';
                            return JSON.stringify({img: imgSrc, name: name,
                                currency: currency, number: number});
                        }""")
                        import json as _json
                        try:
                            info = _json.loads(info_json)
                            img_src = info.get("img", "")
                            name = info.get("name", "")
                            currency = info.get("currency", "")
                            number_str = info.get("number", "")
                        except Exception:
                            img_src, name, currency, number_str = "", "", "", ""

                        # 解析价格
                        price = 0
                        if number_str:
                            try:
                                val = float(number_str.replace(",", ""))
                                if currency == "US$":
                                    val = int(val * _get_usd_jpy_rate())
                                elif currency == "HK$":
                                    val = int(val * 20)
                                elif "." in number_str:
                                    val = int(val * 20)
                                price = int(val)
                            except ValueError:
                                pass

                        items.append({
                            "item_id": item_id,
                            "name": name or "Mercari " + item_id,
                            "price": price,
                            "url": full_url,
                            "image_url": img_src,
                        })
                except Exception:
                    items.append({
                        "item_id": item_id,
                        "name": "Mercari " + item_id,
                        "price": 0,
                        "url": full_url,
                        "image_url": "",
                    })

        except Exception as e:
            logger.error("Playwright搜索出错: {}".format(e))

        browser.close()

    return items


def search(keyword, max_results=10, proxy=None):
    """search_mercari 的短别名"""
    return search_mercari(keyword, max_results, proxy)
