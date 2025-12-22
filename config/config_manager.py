"""
系统配置管理器
用于动态管理系统配置，让配置对核心chat接口生效
"""

import sqlite3
import threading
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """同步配置管理器"""

    _instance = None
    _config_cache = {}
    _db_path = "admin_management.sqlite"
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._conn = None

    def initialize(self):
        """初始化配置管理器"""
        with self._lock:
            try:
                self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
                self._load_config_cache()
                logger.info("配置管理器初始化成功")
            except Exception as e:
                logger.error(f"配置管理器初始化失败: {e}")
                raise

    def _load_config_cache(self):
        """加载配置到缓存"""
        try:
            cursor = self._conn.execute("SELECT key, value FROM system_config")
            rows = cursor.fetchall()

            self._config_cache = {}
            for row in rows:
                self._config_cache[row[0]] = row[1]

            logger.info(f"加载了 {len(self._config_cache)} 个配置项")
        except Exception as e:
            logger.error(f"加载配置缓存失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            try:
                if key in self._config_cache:
                    value = self._config_cache[key]
                    # 类型转换
                    if key.endswith('_timeout') or key.endswith('_length'):
                        return int(value)
                    elif key.endswith('_port'):
                        return int(value)
                    elif key == 'enable_analytics':
                        return value.lower() == 'true'
                    return value
                return default
            except Exception as e:
                logger.error(f"获取配置 {key} 失败: {e}")
                return default

    def set(self, key: str, value: Any) -> bool:
        """设置配置值"""
        with self._lock:
            try:
                # 更新数据库
                self._conn.execute(
                    "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (key, str(value))
                )
                self._conn.commit()

                # 更新缓存
                self._config_cache[key] = str(value)

                logger.info(f"配置 {key} 已更新为: {value}")
                return True
            except Exception as e:
                logger.error(f"设置配置 {key} 失败: {e}")
                return False

    def get_all(self) -> Dict[str, str]:
        """获取所有配置"""
        with self._lock:
            return self._config_cache.copy()

    def reload(self):
        """重新加载配置"""
        with self._lock:
            self._load_config_cache()
            logger.info("配置已重新加载")

    def close(self):
        """关闭数据库连接"""
        with self._lock:
            if self._conn:
                self._conn.close()


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config_value(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数"""
    return config_manager.get(key, default)


def update_config_value(key: str, value: Any) -> bool:
    """更新配置值的便捷函数"""
    return config_manager.set(key, value)


# 预定义的配置项和默认值（合并config.py中的配置）
DEFAULT_CONFIGS = {
    # 管理配置
    "admin_token": "admin123",
    "max_response_length": 2048,
    "response_timeout": 30,
    "enable_analytics": True,

    # 从config.py合并的配置
    "api_timeout": 5,  # 对应config.API_TIMEOUT
    "callback_url": "http://1.95.125.201/wx/send_custom_message",  # 对应config.CALLBACK_URL
    "web_host": "127.0.0.1",  # 对应config.WEB_HOST
    "web_port": 7860,  # 对应config.WEB_PORT
    "web_username": "username",  # 对应config.WEB_USERNAME
    "web_password": "password",  # 对应config.WEB_PASSWORD
    "law_index_name": "law_documents",  # 对应config.LAW_INDEX_NAME
    "checkpoints_db_name": "async_checkpoints.sqlite",  # 对应config.CHECKPOINTS_DB_NAME
    "api_host": "127.0.0.1",  # 对应config.API_HOST
    "api_port": 8000,  # 对应config.API_PORT
}

# 配置项描述
CONFIG_DESCRIPTIONS = {
    "admin_token": "管理员访问Token",
    "max_response_length": "系统给用户的响应最大字符数",
    "response_timeout": "AI响应的最大等待时间（秒）",
    "api_timeout": "API请求超时时间（秒）",
    "enable_analytics": "是否启用用户行为数据分析",
    "callback_url": "微信公众号回调地址",
    "web_host": "Web界面主机地址",
    "web_port": "Web界面端口号",
    "web_username": "Web界面用户名",
    "web_password": "Web界面密码",
    "law_index_name": "法律文档索引名称",
    "checkpoints_db_name": "检查点数据库名称",
    "api_host": "API服务器主机地址",
    "api_port": "API服务器端口号",
}


class SystemConfig:
    """系统配置类，提供配置访问接口"""

    # 管理配置
    @staticmethod
    def get_admin_token() -> str:
        """获取管理员Token"""
        return get_config_value("admin_token", DEFAULT_CONFIGS["admin_token"])

    @staticmethod
    def get_max_response_length() -> int:
        """获取最大响应长度"""
        return get_config_value("max_response_length", DEFAULT_CONFIGS["max_response_length"])

    @staticmethod
    def get_response_timeout() -> int:
        """获取响应超时时间"""
        return get_config_value("response_timeout", DEFAULT_CONFIGS["response_timeout"])

    @staticmethod
    def get_api_timeout() -> int:
        """获取API超时时间"""
        return get_config_value("api_timeout", DEFAULT_CONFIGS["api_timeout"])

    @staticmethod
    def is_analytics_enabled() -> bool:
        """是否启用数据分析"""
        return get_config_value("enable_analytics", DEFAULT_CONFIGS["enable_analytics"])

    @staticmethod
    def get_callback_url() -> str:
        """获取回调URL"""
        return get_config_value("callback_url", DEFAULT_CONFIGS["callback_url"])

    # Web配置
    @staticmethod
    def get_web_host() -> str:
        """获取Web主机地址"""
        return get_config_value("web_host", DEFAULT_CONFIGS["web_host"])

    @staticmethod
    def get_web_port() -> int:
        """获取Web端口号"""
        return get_config_value("web_port", DEFAULT_CONFIGS["web_port"])

    @staticmethod
    def get_web_username() -> str:
        """获取Web用户名"""
        return get_config_value("web_username", DEFAULT_CONFIGS["web_username"])

    @staticmethod
    def get_web_password() -> str:
        """获取Web密码"""
        return get_config_value("web_password", DEFAULT_CONFIGS["web_password"])

    # 系统配置
    @staticmethod
    def get_law_index_name() -> str:
        """获取法律文档索引名称"""
        return get_config_value("law_index_name", DEFAULT_CONFIGS["law_index_name"])

    @staticmethod
    def get_checkpoints_db_name() -> str:
        """获取检查点数据库名称"""
        return get_config_value("checkpoints_db_name", DEFAULT_CONFIGS["checkpoints_db_name"])

    @staticmethod
    def get_api_host() -> str:
        """获取API主机地址"""
        return get_config_value("api_host", DEFAULT_CONFIGS["api_host"])

    @staticmethod
    def get_api_port() -> int:
        """获取API端口号"""
        return get_config_value("api_port", DEFAULT_CONFIGS["api_port"])

    # 更新方法（仅针对可动态更新的配置）
    @staticmethod
    def update_max_response_length(length: int) -> bool:
        """更新最大响应长度"""
        return update_config_value("max_response_length", length)

    @staticmethod
    def update_response_timeout(timeout: int) -> bool:
        """更新响应超时时间"""
        return update_config_value("response_timeout", timeout)

    @staticmethod
    def update_api_timeout(timeout: int) -> bool:
        """更新API超时时间"""
        return update_config_value("api_timeout", timeout)

    @staticmethod
    def update_analytics_enabled(enabled: bool) -> bool:
        """更新数据分析开关"""
        return update_config_value("enable_analytics", enabled)

    @staticmethod
    def update_callback_url(url: str) -> bool:
        """更新回调URL"""
        return update_config_value("callback_url", url)


def init_config_manager():
    """初始化配置管理器"""
    config_manager.initialize()