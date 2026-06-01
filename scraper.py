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
            "extra_http_headers": {
                "Accept-Language": "ja-JP,ja;q=0.9",
            },
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        }
        if proxy and "://" not in proxy:
            proxy = "http://" + proxy
        if proxy and proxy.startswith("http"):
            context_args["proxy"] = {"server": proxy}

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)

            # 等待骨架屏消失（搜索API返回数据）
            try:
                page.wait_for_selector(
                    "li[data-testid='item-cell-skeleton']",
                    state="detached",
                    timeout=30000,
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

                # 尝试从DOM获取图片、名称和价格
                try:
                    name_el = page.query_selector(f"a[href='{link}']")
                    if name_el:
                        info_json = name_el.evaluate("""el => {
                            let card = el.closest('li');
                            if (!card) return '{}';
                            let img = card.querySelector('img');
                            let imgSrc = img ? (img.src || img.getAttribute('data-src') || '') : '';
                            let priceEl = card.querySelector('[class*="price"]') ||
                                         card.querySelector('[class*="Price"]') ||
                                         card.querySelector('[class*="amount"]');
                            let priceText = priceEl ? priceEl.innerText : '';
                            if (!priceText) {
                                let lines = card.innerText.split('\\n');
                                for (let l of lines) {
                                    if (l.match(/[¥￥HK$]\\s*[\\d,]+/)) { priceText = l; break; }
                                }
                            }
                            let nameEl = card.querySelector('[class*="title"]') ||
                                        card.querySelector('[class*="name"]') ||
                                        card.querySelector('h3, h2');
                            let name = nameEl ? nameEl.innerText : el.innerText;
                            return JSON.stringify({img: imgSrc, name: name.trim(), price: priceText.trim()});
                        }""")
                        import json as _json
                        try:
                            info = _json.loads(info_json)
                            img_src = info.get("img", "")
                            name = info.get("name", "")
                            price_text = info.get("price", "")
                        except Exception:
                            img_src = ""
                            name = ""
                            price_text = ""

                        # 清洗名称：移除前导的货币/价格行 (如 "HK$\n176.49\n")
                        name = _re.sub(r'^.*[¥￥HK\$\d,\.]+\s*[\d,\.]+\s*', '', name).strip()

                        # 从价格文本中提取数字
                        # Mercari日本标准价格: ¥12,345 (整数，无小数点)
                        # 如果Chrome区域检测为香港则显示HK$789.00 (浮点数)
                        price = 0
                        if price_text:
                            # 提取所有数字 (包括小数点)
                            all_numbers = _re.findall(r'[\d,]+\.?\d*', price_text.replace(",", ""))
                            for d in all_numbers:
                                try:
                                    val = float(d)
                                    if val > 1:
                                        # 小数点 = 外币价格，估算换算 (HKD→JPY ≈ ×20)
                                        if "." in d:
                                            val = int(val * 20)
                                        price = int(val)
                                        break
                                except ValueError:
                                    continue

                        items.append({
                            "item_id": item_id,
                            "name": name or f"Mercari {item_id}",
                            "price": price,
                            "url": full_url,
                            "image_url": img_src,
                        })
                except Exception:
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
