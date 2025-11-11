"""
B站粉丝牌助手主程序 - 重构版
"""
import asyncio
import itertools
import os
import signal
import sys
import threading
import warnings
from typing import List

import aiohttp

from src import BiliUser, Config, LogManager

__VERSION__ = "1.0.1"

# 忽略时区警告
warnings.filterwarnings(
    "ignore",
    message="The localize method is no longer necessary, as this time zone supports the fold attribute",
)

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class FansMedalHelper:
    """B站粉丝牌助手主类"""

    def __init__(self):
        self.config = Config()
        self.log = LogManager.get_system_logger()
        LogManager.setup_logger()
        self._shutdown_event = asyncio.Event()
        self._current_users = []

    def _signal_handler(self, signum, frame):
        """信号处理器 - 立即退出"""
        self.log.warning(f"接收到信号 {signum}，立即退出...")
        self._shutdown_event.set()

        # 立即退出，不等待任务完成
        try:
            # 尝试优雅清理当前用户资源
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，安排清理任务
                loop.create_task(self._immediate_cleanup())
            else:
                # 如果事件循环未运行，直接清理
                asyncio.run(self._immediate_cleanup())
        except Exception as e:
            self.log.error(f"清理资源时出错: {e}")
        finally:
            self.log.warning("强制退出程序")
            os._exit(0)  # 立即退出，不执行清理代码

    async def _immediate_cleanup(self):
        """立即清理资源"""
        try:
            if self._current_users:
                cleanup_tasks = []
                for user in self._current_users:
                    if hasattr(user, 'session') and not user.session.closed:
                        cleanup_tasks.append(user.session.close())

                if cleanup_tasks:
                    # 设置短超时，快速清理
                    await asyncio.wait_for(
                        asyncio.gather(*cleanup_tasks, return_exceptions=True),
                        timeout=2.0  # 最多等待2秒
                    )
        except asyncio.TimeoutError:
            self.log.warning("清理超时，强制退出")
        except Exception as e:
            self.log.error(f"立即清理失败: {e}")

    def setup_signal_handlers(self):
        """设置信号处理器"""
        # 核心修复：只在主线程中设置信号处理器
        if threading.current_thread() is not threading.main_thread():
            self.log.info("非主线程，跳过信号处理器设置。")
            return

        if sys.platform != "win32":
            # Unix/Linux 系统信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        else:
            # Windows 系统信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

    async def cleanup_users(self):
        """清理所有用户资源"""
        if self._current_users:
            self.log.info("正在清理用户资源...")
            cleanup_tasks = []
            for user in self._current_users:
                if hasattr(user, 'session') and not user.session.closed:
                    cleanup_tasks.append(user.session.close())

            if cleanup_tasks:
                try:
                    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                    self.log.success("用户资源清理完成")
                except Exception as e:
                    self.log.error(f"清理用户资源时出错: {e}")

            self._current_users.clear()

    async def initialize_users(self, users_config: List[dict]) -> List[BiliUser]:
        """初始化用户列表"""
        users = []
        init_tasks = []

        for user_config in users_config:
            if not user_config.get("access_key"):
                continue

            bili_user = BiliUser(
                user_config["access_key"],
                user_config.get("white_uid", ""),
                user_config.get("banned_uid", ""),
                self._merge_user_config(user_config),
            )

            users.append(bili_user)
            init_tasks.append(bili_user.init())

        # 保存用户列表以便清理
        self._current_users = users

        # 并发初始化所有用户
        if init_tasks:
            try:
                await asyncio.gather(*init_tasks)
            except Exception as e:
                self.log.error(f"用户初始化失败: {e}")
                await self.cleanup_users()
                raise

        return users

    def _merge_user_config(self, user_config: dict) -> dict:
        """合并用户配置和全局配置"""
        merged_config = self.config.config.copy()

        # 用户级别配置项（会覆盖全局配置）
        user_specific_keys = [
            'coin_remain', 'coin_uid', 'coin_max', 'coin_max_per_uid'
        ]

        for key in user_specific_keys:
            if key in user_config:
                merged_config[key] = user_config[key]

        return merged_config

    async def execute_tasks(self, users: List[BiliUser]) -> List[str]:
        """执行所有用户的任务"""
        message_list = []

        try:
            # 检查是否收到退出信号
            if self._shutdown_event.is_set():
                self.log.warning("检测到退出信号，取消任务执行")
                return ["任务被用户中断"]

            # 按照原始项目的逻辑：直接并发执行所有用户的任务
            start_tasks = [user.start() for user in users]
            await asyncio.gather(*start_tasks, return_exceptions=True)

        except KeyboardInterrupt:
            self.log.warning("检测到键盘中断 (Ctrl+C)")
            message_list.append("任务被用户中断")
        except Exception as e:
            self.log.exception(f"任务执行异常: {e}")
            message_list.append(f"任务执行失败: {e}")

        finally:
            # 如果收到退出信号，跳过消息收集
            if self._shutdown_event.is_set():
                self.log.info("收到退出信号，跳过消息收集")
                return message_list or ["任务被中断"]

            try:
                # 收集所有用户的消息
                msg_tasks = [user.send_msg() for user in users]
                user_messages = await asyncio.gather(*msg_tasks, return_exceptions=True)

                # 过滤掉异常结果
                valid_messages = [
                    msg for msg in user_messages if not isinstance(msg, Exception)]
                message_list.extend(
                    list(itertools.chain.from_iterable(valid_messages)))
            except Exception as e:
                self.log.error(f"消息收集失败: {e}")
                message_list.append(f"消息收集失败: {e}")

        return message_list

    async def push_notifications(self, session: aiohttp.ClientSession, messages: List[str]):
        """推送通知"""
        try:
            notification_config = self.config.get_notification_config()

            # 推送到Server酱
            if notification_config.get("SENDKEY"):
                await self._push_to_server_chan(session, notification_config["SENDKEY"], messages)

            # 推送到其他平台
            if notification_config.get("MOREPUSH"):
                await self._push_to_more_platforms(messages, notification_config["MOREPUSH"])

        except Exception as e:
            self.log.error(f"推送通知失败: {e}")

    async def _push_to_server_chan(self, session: aiohttp.ClientSession, sendkey: str, messages: List[str]):
        """推送到Server酱"""
        content = "  \n".join(messages)
        data = {
            "text": "【B站粉丝牌助手推送】",
            "desp": content
        }

        try:
            async with session.post(f"https://sctapi.ftqq.com/{sendkey}.send", data=data) as resp:
                if resp.status == 200:
                    self.log.success("Server酱推送成功")
                else:
                    self.log.error(f"Server酱推送失败: {resp.status}")
        except Exception as e:
            self.log.error(f"Server酱推送异常: {e}")

    async def _push_to_more_platforms(self, messages: List[str], morepush_config: dict):
        """推送到更多平台"""
        try:
            from onepush import notify

            notifier = morepush_config["notifier"]
            params = morepush_config["params"]

            notify(
                notifier,
                title="【B站粉丝牌助手推送】",
                content="  \n".join(messages),
                **params,
                proxy=self.config.get("PROXY"),
            )

            self.log.success(f"{notifier} 推送成功")

        except ImportError:
            self.log.warning("onepush 库未安装，跳过推送")
        except Exception as e:
            self.log.error(f"推送异常: {e}")

    async def run(self):
        """运行主程序"""
        self.log.warning(f"当前版本为: {__VERSION__}")

        session = aiohttp.ClientSession(trust_env=True)

        try:
            # 设置信号处理器
            self.setup_signal_handlers()

            # 初始化用户
            users = await self.initialize_users(self.config.get_users())

            if not users:
                self.log.warning("没有有效的用户配置")
                return

            # 检查退出信号
            if self._shutdown_event.is_set():
                self.log.warning("程序启动期间收到退出信号")
                return

            # 执行任务
            messages = await self.execute_tasks(users)

            # 输出消息到日志
            for message in messages:
                self.log.info(message)

            # 推送通知（如果没有被中断）
            if not self._shutdown_event.is_set():
                await self.push_notifications(session, messages)
            else:
                self.log.info("由于程序被中断，跳过推送通知")

        except KeyboardInterrupt:
            self.log.warning("程序被用户中断 (Ctrl+C)")
        except SystemExit:
            self.log.info("程序正常退出")
        except Exception as e:
            self.log.exception(f"程序运行异常: {e}")

        finally:
            # 清理资源
            try:
                await self.cleanup_users()
                await session.close()
                self.log.info("程序资源清理完成")
            except Exception as e:
                self.log.error(f"资源清理时出错: {e}")

            self.log.info("程序退出")


async def main():
    """主函数"""
    helper = FansMedalHelper()
    await helper.run()


def run_with_scheduler():
    """使用定时器运行"""
    try:
        config = Config()
        notification_config = config.get_notification_config()
        cron = notification_config.get("CRON")

        log = LogManager.get_system_logger()

        if cron:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger

            log.info(f"使用内置定时器 {cron}，开启定时任务")
            scheduler = BlockingScheduler()
            scheduler.add_job(
                lambda: asyncio.run(main()),
                CronTrigger.from_crontab(cron),
                misfire_grace_time=3600
            )

            try:
                scheduler.start()
            except KeyboardInterrupt:
                log.warning("定时任务被用户中断")
                scheduler.shutdown(wait=True)

        elif "--auto" in sys.argv:
            import datetime

            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.interval import IntervalTrigger

            log.info("使用自动守护模式，每隔 24 小时运行一次")
            scheduler = BlockingScheduler(timezone="Asia/Shanghai")
            scheduler.add_job(
                lambda: asyncio.run(main()),
                IntervalTrigger(hours=24),
                next_run_time=datetime.datetime.now(),
                misfire_grace_time=3600,
            )

            try:
                scheduler.start()
            except KeyboardInterrupt:
                log.warning("守护任务被用户中断")
                scheduler.shutdown(wait=True)

        else:
            log.info("未配置定时器，开启单次任务")
            try:
                asyncio.run(main())
            except KeyboardInterrupt:
                log.warning("单次任务被用户中断")
            except Exception as e:
                log.error(f"任务执行异常: {e}")
                raise
            log.info("任务结束")

    except KeyboardInterrupt:
        log.warning("程序被用户中断")
        sys.exit(0)
    except SystemExit:
        log.info("程序正常退出")
    except Exception as e:
        log.error(f"程序启动失败: {e}")
        sys.exit(1)


def run(*args, **kwargs):
    """兼容旧版本的run函数"""
    run_with_scheduler()


if __name__ == "__main__":
    run_with_scheduler()
