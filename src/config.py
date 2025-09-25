"""
配置管理模块
"""
import json
import os
from typing import Any, Dict, List

import yaml

from .exceptions import ConfigError


class Config:
    """配置管理类"""

    DEFAULT_CONFIG = {
        "ASYNC": 1,
        "LIKE_CD": 1,
        "DANMAKU_CD": 3,
        "DANMAKU_NUM": 10,
        "WATCHINGLIVE": 45,
        "WEARMEDAL": 1,
        "SIGNINGROUP": 2,
        "PROXY": "",
        "coin_remain": 0,
        "coin_uid": 0,
        "coin_max": 0,
        "coin_max_per_uid": 10,
    }

    def __init__(self):
        self._raw_config = None
        self.config = self._load_config()
        self.users_config = self._extract_users_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if os.environ.get("USERS"):
                users = json.loads(os.environ.get("USERS"))
            else:
                with open("users.yaml", "r", encoding="utf-8") as f:
                    users = yaml.load(f, Loader=yaml.FullLoader)

            self._raw_config = users
            self._validate_config(users)
            return self._extract_config(users)

        except FileNotFoundError:
            raise ConfigError("配置文件 users.yaml 不存在")
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML 文件格式错误: {e}")
        except json.JSONDecodeError as e:
            raise ConfigError(f"JSON 格式错误: {e}")
        except Exception as e:
            raise ConfigError(f"读取配置文件失败: {e}")

    def _validate_config(self, users: Dict[str, Any]) -> None:
        """验证配置参数"""
        validations = [
            ("ASYNC", users.get("ASYNC"), [0, 1], "ASYNC参数错误，必须为0或1"),
            ("LIKE_CD", users.get("LIKE_CD"),
             lambda x: x >= 0, "LIKE_CD参数错误，必须>=0"),
            ("DANMAKU_CD", users.get("DANMAKU_CD"),
             lambda x: x >= 0, "DANMAKU_CD参数错误，必须>=0"),
            ("DANMAKU_NUM", users.get("DANMAKU_NUM"),
             lambda x: x >= 0, "DANMAKU_NUM参数错误，必须>=0"),
            ("WATCHINGLIVE", users.get("WATCHINGLIVE"),
             lambda x: x >= 0, "WATCHINGLIVE参数错误，必须>=0"),
            ("WEARMEDAL", users.get("WEARMEDAL"),
             [0, 1], "WEARMEDAL参数错误，必须为0或1"),
        ]

        for param_name, param_value, validation, error_msg in validations:
            if param_value is None:
                continue

            if callable(validation):
                if not validation(param_value):
                    raise ConfigError(error_msg)
            else:
                if param_value not in validation:
                    raise ConfigError(error_msg)

    def _extract_config(self, users: Dict[str, Any]) -> Dict[str, Any]:
        """提取配置参数"""
        config = self.DEFAULT_CONFIG.copy()

        # 更新用户配置
        for key in config.keys():
            if key in users:
                config[key] = users[key]

        return config

    def _extract_users_config(self) -> List[Dict[str, Any]]:
        """提取用户配置"""
        if not self._raw_config:
            return []

        return self._raw_config.get("USERS", [])

    def get_users(self) -> List[Dict[str, Any]]:
        """获取用户配置列表"""
        return self.users_config

    def get_notification_config(self) -> Dict[str, Any]:
        """获取通知配置"""
        if not self._raw_config:
            return {}

        return {
            "SENDKEY": self._raw_config.get("SENDKEY"),
            "MOREPUSH": self._raw_config.get("MOREPUSH"),
            "CRON": self._raw_config.get("CRON"),
        }

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.config[key]

    def validate_user_config(self, user_config: Dict[str, Any]) -> bool:
        """验证单个用户配置"""
        required_fields = ["access_key"]

        for field in required_fields:
            if not user_config.get(field):
                return False

        return True
