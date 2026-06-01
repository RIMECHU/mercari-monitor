"""
DigiMart (digimart.net) 搜索爬虫 — 乐器交易平台
"""
import logging
import re
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DIGIMART_BASE = "https://www.digimart.net"


def search_digimart(keyword, max_results=10, proxy=None):
    """
    搜索 DigiMart
    返回: list[dict] — [{"item_id", "name", "price", "url", "image_url"}, ...]
    """
    search_url = f"{DIGIMART_BASE}/search"
    params = {"keyword": keyword}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }

    client_kwargs = {"timeout": 20}
    if proxy:
        client_kwargs["proxy"] = proxy

    items = []
    try:
        with httpx.Client(**client_kwargs) as client:
            resp = client.get(search_url, params=params, headers=headers)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # DigiMart 商品列表: div.itemSearchBlock
        blocks = soup.select("div.itemSearchBlock")
        count = 0

        for block in blocks:
            if count >= max_results:
                break

            try:
                # 商品ID
                item_id = block.get("data-instrument-cd", "")

                # 商品标题和链接
                title_el = block.select_one("p.ttl a")
                if not title_el:
                    continue
                name = title_el.text.strip()
                item_url = title_el.get("href", "")
                if item_url and not item_url.startswith("http"):
                    item_url = DIGIMART_BASE + item_url

                # 价格 (第一个 p.price 的文本)
                price_el = block.select_one("p.price")
                if not price_el:
                    continue
                price_text = price_el.get_text(strip=True)
                # 提取数字: "¥462000税込" → 462000
                price_match = re.search(r'(\d[\d,]*)', price_text)
                if not price_match:
                    continue
                price = int(price_match.group(1).replace(",", ""))

                # 图片
                img_el = block.select_one("div.pic img")
                image_url = ""
                if img_el:
                    src = img_el.get("src", "")
                    if src.startswith("//"):
                        image_url = "https:" + src
                    elif src.startswith("/"):
                        image_url = DIGIMART_BASE + src
                    else:
                        image_url = src

                items.append({
                    "item_id": item_id,
                    "name": name,
                    "price": price,
                    "url": item_url,
                    "image_url": image_url,
                })
                count += 1

            except Exception as e:
                logger.debug(f"解析单个商品失败: {e}")
                continue

        logger.info(f"DigiMart 搜索 '{keyword}': 找到 {len(items)} 个结果")

    except Exception as e:
        logger.error(f"DigiMart 搜索失败: {e}")
        return []

    return items
