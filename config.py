"""
配置管理模块 — 读写 config.json
"""
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    "sendkey": "",
    "check_interval_minutes": 30,
    "max_results_per_search": 10,
    "run_on_startup": True,
    "notification_enabled": True,
    "proxy": "",
}


def load_config():
    """加载配置，如文件不存在则用默认值创建"""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 合并不存在的默认键
    changed = False
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
            changed = True

    if changed:
        save_config(config)

    return config


def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_effective_sendkey():
    """获取SendKey，环境变量优先于配置文件"""
    env_key = os.environ.get('MERCARI_MONITOR_SENDKEY', '')
    if env_key:
        return env_key
    config = load_config()
    return config.get('sendkey', '')


def mask_sendkey(key):
    """脱敏显示SendKey: 'SCT1****xyz'"""
    if not key or len(key) < 8:
        return key
    return key[:4] + "****" + key[-3:]
