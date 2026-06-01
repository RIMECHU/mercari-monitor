"""
Mercari Monitor — 系统托盘应用
启动Flask服务并在系统托盘显示图标，支持开机自启
"""
import os
import sys
import threading
import webbrowser
import logging

# 确保项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "monitor.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("tray")

# ── Flask 在后台线程启动 ──
from waitress import serve
from app import app, boot

def start_server():
    """在后台线程启动 Flask 服务"""
    try:
        boot()
        port = int(os.environ.get("PORT", 5000))
        logger.info(f"服务启动: http://localhost:{port}")
        serve(app, host="0.0.0.0", port=port, _quiet=True)
    except Exception as e:
        logger.error(f"服务启动失败: {e}")

server_thread = threading.Thread(target=start_server, daemon=True)

# ── 系统托盘 ──
import pystray
from PIL import Image, ImageDraw

def create_icon_image():
    """创建托盘图标 (红色圆点 + M 字母)"""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 红色圆形背景
    draw.ellipse([2, 2, 30, 30], fill=(229, 57, 53))
    # 白色 M
    draw.text((8, 6), "M", fill=(255, 255, 255))
    return img

def on_open(icon, item):
    """打开监控面板"""
    webbrowser.open("http://localhost:5000")

def on_exit(icon, item):
    """退出应用"""
    logger.info("用户退出托盘应用")
    icon.stop()
    os._exit(0)

def setup_tray():
    """创建并运行系统托盘图标"""
    icon = pystray.Icon(
        "mercari_monitor",
        create_icon_image(),
        "Mercari 价格监控",
        menu=pystray.Menu(
            pystray.MenuItem("📊 打开监控面板", on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ 退出", on_exit),
        ),
    )
    return icon

# ── 开机自启动设置 ──

def get_startup_path():
    """获取开机启动 VBS 脚本路径"""
    startup_dir = os.path.join(
        os.environ["APPDATA"],
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )
    return os.path.join(startup_dir, "MercariMonitor.vbs")

def enable_autostart():
    """启用开机自启动 — 在启动文件夹创建VBS脚本"""
    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    vbs_path = get_startup_path()

    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run """{python_exe}"" ""{script_path}""", 7, False\n'
    )
    with open(vbs_path, "w", encoding="ascii") as f:
        f.write(vbs_content)

    logger.info(f"开机自启动已启用: {vbs_path}")
    return vbs_path

def disable_autostart():
    """关闭开机自启动"""
    vbs_path = get_startup_path()
    if os.path.exists(vbs_path):
        os.remove(vbs_path)
        logger.info("开机自启动已关闭")

def is_autostart_enabled():
    """检查是否已设置开机自启"""
    return os.path.exists(get_startup_path())


# ── 主入口 ──
if __name__ == "__main__":
    logger.info("=" * 40)
    logger.info("Mercari Monitor 托盘应用启动")

    # 启动 Flask 服务
    server_thread.start()
    logger.info("Web服务线程已启动")

    # 自动启用开机自启动（首次运行）
    if not is_autostart_enabled():
        try:
            enable_autostart()
            logger.info("已自动设置开机自启")
        except Exception as e:
            logger.warning(f"设置开机自启失败: {e}")

    # 显示托盘图标
    tray_icon = setup_tray()
    try:
        tray_icon.run()
    except KeyboardInterrupt:
        logger.info("托盘应用已退出")
