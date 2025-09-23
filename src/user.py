"""
用户管理模块 - 重构版
"""
import asyncio
import uuid
from typing import Any, Dict, List

from aiohttp import ClientSession, ClientTimeout

from .api import BiliApi
from .constants import BiliConstants
from .exceptions import LoginError
from .logger_manager import LogManager
from .services import (AuthService, DanmakuService, GroupService,
                       HeartbeatService, LikeService, MedalService, CoinService)
from .stats_service import StatsService


class BiliUser:
    """B站用户类"""

    def __init__(self, access_token: str, white_uids: str = '', banned_uids: str = '', config: Dict[str, Any] = None):
        # 基本信息
        self.mid: int = 0
        self.name: str = ""
        self.access_key: str = access_token
        self.config: Dict[str, Any] = config or {}
        self.is_login: bool = False

        # 解析白名单和黑名单
        self._parse_uid_lists(white_uids, banned_uids)

        # 勋章列表
        self.medals: List[Dict[str, Any]] = []
        self.medalsNeedDo: List[Dict[str, Any]] = []
        self.medalsOthers: List[Dict[str, Any]] = []
        self.medalsLiving: List[Dict[str, Any]] = []
        self.medalsNoLiving: List[Dict[str, Any]] = []

        # 会话和API
        self.session = ClientSession(
            timeout=ClientTimeout(total=3), trust_env=True)
        self.api = BiliApi(self, self.session)

        # 业务服务层
        self.auth_service = AuthService(self.api)
        self.medal_service = MedalService(
            self.api, self.whiteList, self.bannedList)
        self.like_service = LikeService(self.api)
        self.danmaku_service = DanmakuService(self.api)
        self.heartbeat_service = HeartbeatService(self.api)
        self.group_service = GroupService(self.api)
        self.coin_service = CoinService(self.api, self.whiteList, self.bannedList)
        self.stats_service = None  # 将在登录验证后初始化

        # 任务状态
        self.retry_times: int = 0
        self.max_retry_times: int = BiliConstants.Tasks.MAX_RETRY_TIMES
        self.message: List[str] = []
        self.errmsg: List[str] = ["错误日志："]
        self.uuids: List[str] = [str(uuid.uuid4()) for _ in range(2)]

        # 日志
        self.log = LogManager.get_system_logger()  # 初始化系统日志，登录成功后会更新为用户专用日志

    def _parse_uid_lists(self, white_uids: str, banned_uids: str):
        """解析白名单和黑名单"""
        try:
            self.whiteList = [
                int(x) if x else 0 for x in str(white_uids).split(',')]
            self.bannedList = [
                int(x) if x else 0 for x in str(banned_uids).split(',')]
        except ValueError:
            raise ValueError("白名单或黑名单格式错误")

    async def login_verify(self) -> bool:
        """登录验证"""
        try:
            user_info = await self.auth_service.execute()
            self.mid = user_info.mid
            self.name = user_info.name

            # 初始化日志和统计服务
            self.log = LogManager.get_logger(self.name)
            self.stats_service = StatsService(self.api, self.name, self.log)

            # 重新初始化服务，使用用户专有的日志记录器
            self.medal_service = MedalService(
                self.api, self.whiteList, self.bannedList, self.log)
            self.like_service = LikeService(self.api, self.log)
            self.danmaku_service = DanmakuService(self.api, self.log)
            self.heartbeat_service = HeartbeatService(self.api, self.log)
            self.group_service = GroupService(self.api, self.log)
            self.coin_service = CoinService(self.api, self.whiteList, self.bannedList, self.log)

            # 获取初始佩戴勋章信息
            if user_info.medal:
                medal_info = await self.api.getMedalsInfoByUid(user_info.medal['target_id'])
                if medal_info.get('has_fans_medal'):
                    self.initialMedal = medal_info['my_fans_medal']

            self.log.success(f"{self.mid} 登录成功")
            self.is_login = True
            return True

        except LoginError as e:
            self.log.error(f"登录失败: {e}")
            self.errmsg.append(f"登录失败: {e}")
            self.is_login = False
            return False
        except Exception as e:
            self.log.error(f"登录异常: {e}")
            self.errmsg.append(f"登录异常: {e}")
            self.is_login = False
            return False

    async def get_medals(self, show_logs: bool = True):
        """获取用户勋章"""
        classified_medals = await self.medal_service.execute(show_logs)

        # 清空原有勋章列表
        self._clear_medal_lists()

        # 设置分类后的勋章
        self.medalsNeedDo = classified_medals['need_do']
        self.medalsOthers = classified_medals['others']
        self.medalsLiving = classified_medals['living']
        self.medalsNoLiving = classified_medals['no_living']

        # 保持兼容性
        self.medals = self.medalsNeedDo + self.medalsOthers

    def _clear_medal_lists(self):
        """清空勋章列表"""
        for attr in ['medals', 'medalsNeedDo', 'medalsOthers', 'medalsLiving', 'medalsNoLiving']:
            getattr(self, attr).clear()

    async def init(self):
        """初始化用户"""
        if not await self.login_verify():
            self.log.error("登录失败 可能是 access_key 过期 , 请重新获取")
            self.errmsg.append("登录失败 可能是 access_key 过期 , 请重新获取")
            await self.session.close()

    async def start(self):
        """开始执行任务"""
        if not self.is_login:
            return

        # 获取勋章信息
        await self.get_medals()

        tasks = []

        if self.medalsNeedDo:
            self.log.info(f"共有 {len(self.medalsNeedDo)} 个牌子未满 30 亲密度")
            tasks.extend([
                self.like_service.execute(self.medalsLiving, self.config),
                self.heartbeat_service.execute(self.medalsNeedDo, self.config),
            ])
        else:
            self.log.info("所有牌子已满 30 亲密度")

        # 执行弹幕和应援团任务
        tasks.extend([
            self.danmaku_service.execute(self.medalsNoLiving, self.config),
            self.group_service.execute(self.config),
        ])

        # 执行投币任务并获取结果
        coin_result = await self.coin_service.execute(self.config)
        
        # 将投币结果传递给统计服务
        if hasattr(self, 'stats_service') and self.stats_service:
            self.stats_service.set_coin_stats(coin_result)

        # 等待其他任务完成（维持原始程序逻辑）
        await asyncio.gather(*tasks, return_exceptions=True)

    async def send_msg(self):
        """发送消息统计"""
        if not self.is_login:
            await self.session.close()
            return self.message + self.errmsg

        # 重新获取勋章数据以确保统计的准确性（按照原始项目逻辑，不显示日志）
        await self.get_medals(show_logs=False)

        # 使用统计服务生成报告
        initial_medal = getattr(self, 'initialMedal', None)
        report_messages = await self.stats_service.execute(self.medals, initial_medal)
        self.message.extend(report_messages)

        await self.session.close()
        return self.message + self.errmsg + ['---']

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.session.close()
