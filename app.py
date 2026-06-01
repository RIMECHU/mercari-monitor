"""
Mercari Japan 价格监控器 — Flask 主程序
"""
import os
import sys
import logging
import threading
from datetime import datetime

from flask import Flask, render_template, request, jsonify

from db import init_db
from config import load_config, save_config, mask_sendkey, get_effective_sendkey
from models import (
    add_product, get_all_products, delete_product, toggle_product,
    get_price_history, get_product, get_stats,
)
from scheduler_job import check_all_active_products, check_single_product
from notifier import send_test_notification

# ── 日志配置 ──
# Windows控制台默认使用GBK编码，需要重配置为UTF-8以支持emoji和日文字符
sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "monitor.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

# ── Flask 应用 ──
app = Flask(__name__)

# ── APScheduler ──
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler(daemon=True)
_scheduler_started = False


def start_scheduler(interval_minutes=None):
    """启动定时任务"""
    global _scheduler_started
    if interval_minutes is None:
        config = load_config()
        interval_minutes = config.get("check_interval_minutes", 30)

    # 如果已有任务则更新
    if scheduler.get_job("price_check_job"):
        scheduler.reschedule_job(
            "price_check_job",
            trigger=IntervalTrigger(minutes=interval_minutes, jitter=60),
        )
        logger.info(f"调度器已更新: 每 {interval_minutes} 分钟检查一次")
    else:
        scheduler.add_job(
            func=check_all_active_products,
            trigger=IntervalTrigger(minutes=interval_minutes, jitter=60),
            id="price_check_job",
            name="自动价格检查",
            replace_existing=True,
        )
        logger.info(f"调度器已启动: 每 {interval_minutes} 分钟检查一次")

    if not _scheduler_started and not scheduler.running:
        scheduler.start()
        _scheduler_started = True


# ── 路由：页面 ──

@app.route("/")
def index():
    """主页面"""
    return render_template("index.html")


# ── 路由：商品管理 API ──

@app.route("/api/products", methods=["GET"])
def api_get_products():
    """获取所有监控商品及最新价格摘要"""
    try:
        products = get_all_products()
        return jsonify({"products": products})
    except Exception as e:
        logger.error(f"获取商品列表失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/products", methods=["POST"])
def api_add_product():
    """添加监控商品"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        keyword = data.get("keyword", "").strip()
        target_price = data.get("target_price")

        if not keyword:
            return jsonify({"error": "关键词不能为空"}), 400
        if not target_price or int(target_price) <= 0:
            return jsonify({"error": "目标价格必须大于0"}), 400

        product_id = add_product(keyword, int(target_price))
        logger.info(f"添加监控: [{product_id}] {keyword} 目标价: ¥{target_price}")

        return jsonify({"id": product_id, "message": "添加成功"}), 201
    except Exception as e:
        logger.error(f"添加商品失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def api_delete_product(product_id):
    """删除监控商品"""
    try:
        product = get_product(product_id)
        if not product:
            return jsonify({"error": "商品不存在"}), 404
        delete_product(product_id)
        logger.info(f"删除监控: [{product_id}] {product['keyword']}")
        return jsonify({"message": "删除成功"})
    except Exception as e:
        logger.error(f"删除商品失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<int:product_id>/toggle", methods=["PUT"])
def api_toggle_product(product_id):
    """切换商品激活/暂停状态"""
    try:
        new_state = toggle_product(product_id)
        if new_state is None:
            return jsonify({"error": "商品不存在"}), 404
        status_text = "监控中" if new_state else "已暂停"
        logger.info(f"[{product_id}] 状态切换: {status_text}")
        return jsonify({"active": new_state, "status_text": status_text})
    except Exception as e:
        logger.error(f"切换状态失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<int:product_id>/history", methods=["GET"])
def api_product_history(product_id):
    """获取商品价格历史"""
    try:
        limit = request.args.get("limit", 50, type=int)
        product = get_product(product_id)
        if not product:
            return jsonify({"error": "商品不存在"}), 404

        history = get_price_history(product_id, limit)
        # 添加低于目标价标记
        target = product["target_price"]
        for h in history:
            h["below_target"] = h["item_price"] <= target

        return jsonify({
            "product_id": product_id,
            "keyword": product["keyword"],
            "target_price": target,
            "history": history,
        })
    except Exception as e:
        logger.error(f"获取价格历史失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/products/<int:product_id>/check", methods=["POST"])
def api_check_single_product(product_id):
    """手动检查单个商品"""
    try:
        # 在后台线程执行，避免阻塞请求
        result = {"found": 0, "alerts": 0}

        def _run():
            nonlocal result
            result = check_single_product(product_id)

        thread = threading.Thread(target=_run)
        thread.start()
        thread.join(timeout=30)

        return jsonify({
            "message": f"检查完成: 找到 {result.get('found', 0)} 个商品, 发送 {result.get('alerts', 0)} 条提醒",
            **result,
        })
    except Exception as e:
        logger.error(f"手动检查失败: {e}")
        return jsonify({"error": str(e)}), 500


# ── 路由：配置与统计 API ──

@app.route("/api/config", methods=["GET"])
def api_get_config():
    """获取当前配置（SendKey脱敏）"""
    try:
        config = load_config()
        config["sendkey"] = mask_sendkey(config.get("sendkey", ""))
        config["sendkey_configured"] = bool(get_effective_sendkey())
        return jsonify(config)
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["PUT"])
def api_update_config():
    """更新配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        config = load_config()

        if "sendkey" in data and data["sendkey"]:
            # 如果用户输入的不是脱敏后的值，才更新
            if "****" not in data["sendkey"]:
                config["sendkey"] = data["sendkey"].strip()

        if "check_interval_minutes" in data:
            interval = int(data["check_interval_minutes"])
            if interval < 1:
                return jsonify({"error": "检查间隔至少1分钟"}), 400
            config["check_interval_minutes"] = interval

        if "max_results_per_search" in data:
            max_r = int(data["max_results_per_search"])
            if max_r < 1 or max_r > 50:
                return jsonify({"error": "搜索结果数应在1-50之间"}), 400
            config["max_results_per_search"] = max_r

        if "notification_enabled" in data:
            config["notification_enabled"] = bool(data["notification_enabled"])

        if "proxy" in data:
            config["proxy"] = data.get("proxy", "").strip()

        if "run_on_startup" in data:
            config["run_on_startup"] = bool(data["run_on_startup"])

        save_config(config)

        # 更新调度器间隔
        start_scheduler(config["check_interval_minutes"])

        logger.info("配置已更新")
        return jsonify({"message": "配置已保存", "config": {**config, "sendkey": mask_sendkey(config["sendkey"])}})
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/check-all", methods=["POST"])
def api_check_all():
    """手动触发全量检查"""
    try:
        def _run():
            check_all_active_products()

        thread = threading.Thread(target=_run)
        thread.start()
        return jsonify({"message": "全量检查已触发，请查看日志"})
    except Exception as e:
        logger.error(f"触发全量检查失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """获取仪表盘统计"""
    try:
        stats = get_stats()

        # 获取下次检查时间
        job = scheduler.get_job("price_check_job")
        next_check = None
        if job and job.next_run_time:
            next_check = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")

        stats["next_check_at"] = next_check
        return jsonify(stats)
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-notification", methods=["POST"])
def api_test_notification():
    """测试Server酱推送"""
    try:
        sendkey = get_effective_sendkey()
        if not sendkey:
            return jsonify({"error": "SendKey 未配置，请先在设置中配置"}), 400

        success = send_test_notification(sendkey)
        if success:
            return jsonify({"message": "测试消息已发送，请检查微信"})
        else:
            return jsonify({"error": "发送失败，请检查SendKey是否正确"}), 500
    except Exception as e:
        logger.error(f"测试通知失败: {e}")
        return jsonify({"error": str(e)}), 500


# ── 应用启动 ──

def boot():
    """应用启动初始化"""
    logger.info("=" * 50)
    logger.info("Mercari Japan 价格监控器 启动中...")
    logger.info("=" * 50)

    # 初始化数据库
    init_db()
    logger.info("数据库已初始化")

    # 加载配置
    config = load_config()
    logger.info(f"配置加载完成 (检查间隔: {config['check_interval_minutes']}分钟)")

    if not get_effective_sendkey():
        logger.warning("⚠ Server酱 SendKey 未配置！请在设置页面配置")

    # 启动调度器
    start_scheduler()

    # 启动时立即检查一次
    if config.get("run_on_startup", True):
        logger.info("启动时执行首次检查...")
        def _initial_check():
            try:
                check_all_active_products()
            except Exception as e:
                logger.error(f"首次检查失败: {e}")
        threading.Thread(target=_initial_check).start()

    logger.info(f"访问 http://localhost:5000 打开监控面板")


# 处理应用退出
import atexit


@atexit.register
def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已关闭")


if __name__ == "__main__":
    boot()

    # 云端部署使用 waitress/gunicorn，本地开发用 Flask 内置服务器
    # 通过环境变量 DEPLOY 区分
    if os.environ.get("DEPLOY") == "cloud":
        from waitress import serve
        port = int(os.environ.get("PORT", 5000))
        logger.info(f"生产模式启动 (waitress): 0.0.0.0:{port}")
        serve(app, host="0.0.0.0", port=port)
    else:
        app.run(host="0.0.0.0", port=5000, debug=False)
