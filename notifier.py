"""
Server酱 (ServerChan) 微信推送通知模块
API文档: https://sct.ftqq.com/
"""
import requests
import random
import time
import logging

logger = logging.getLogger(__name__)

SERVERCHAN_API = "https://sctapi.ftqq.com"


def send_price_alert(sendkey, keyword, target_price, item_name, item_price, item_url, image_url=""):
    """
    发送降价提醒到微信
    返回: True=成功, False=失败
    """
    diff = target_price - item_price
    title = f"🔻 降价提醒: {keyword}"

    # 构建Markdown消息内容
    desp_lines = [
        f"## 降价提醒",
        f"",
        f"- **监控关键词**: {keyword}",
        f"- **目标价格**: ¥{target_price:,}",
        f"- **当前价格**: ¥{item_price:,} (低于目标 ¥{diff:,})",
        f"- **商品名称**: [{item_name}]({item_url})",
        f"- **商品链接**: {item_url}",
        f"",
    ]
    if image_url:
        desp_lines.append(f"![商品图片]({image_url})")
        desp_lines.append(f"")

    desp_lines.append(f"---")
    desp_lines.append(f"*检查时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*")

    desp = "\n".join(desp_lines)

    # 标题加随机后缀防止Server酱去重
    title = f"{title} [{random.randint(1000, 9999)}]"

    try:
        resp = requests.post(
            f"{SERVERCHAN_API}/{sendkey}.send",
            data={"title": title, "desp": desp},
            timeout=10,
        )
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"推送成功: {item_name} - ¥{item_price}")
            return True
        else:
            logger.warning(f"Server酱返回错误: {result}")
            return False
    except Exception as e:
        logger.error(f"推送失败: {e}")
        return False


def send_test_notification(sendkey):
    """发送测试通知，验证Server酱配置"""
    title = f"✅ Mercari Monitor 测试消息 [{random.randint(1000, 9999)}]"
    desp = (
        "如果你收到这条消息，说明 **Server酱** 配置成功！\n\n"
        "Mercari Japan 价格监控已就绪，当商品价格低于目标价时会自动提醒你。"
    )
    try:
        resp = requests.post(
            f"{SERVERCHAN_API}/{sendkey}.send",
            data={"title": title, "desp": desp},
            timeout=10,
        )
        result = resp.json()
        return result.get("code") == 0
    except Exception as e:
        logger.error(f"测试推送失败: {e}")
        return False
