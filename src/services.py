"""
业务服务层模块
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
import asyncio

from .api import BiliApi
from .models import Medal, MedalWithRoom, UserInfo, Group
from .exceptions import BiliException, LoginError
from .logger_manager import LogManager
from .utils import safe_get
from .constants import BiliConstants


class BaseService(ABC):
    """基础服务抽象类"""

    def __init__(self, api: BiliApi, logger=None):
        self.api = api
        self.log = logger or LogManager.get_system_logger()

    @abstractmethod
    async def execute(self, *args, **kwargs):
        """执行服务方法"""
        pass


class AuthService(BaseService):
    """用户认证服务"""

    async def login_verify(self) -> UserInfo:
        """登录验证"""
        try:
            login_info = await self.api.loginVerift()
            mid = login_info.get('mid', 0)
            name = login_info.get('uname', '')

            if mid == 0:
                raise LoginError("登录失败，可能是 access_key 过期")

            # 获取用户详细信息
            user_info = await self.api.getUserInfo()
            return UserInfo(
                mid=mid,
                name=name,
                medal=user_info.get('medal'),
                raw_data=login_info
            )
        except Exception as e:
            raise LoginError(f"登录验证失败: {e}")

    async def execute(self, *args, **kwargs) -> UserInfo:
        """执行登录验证"""
        return await self.login_verify()


class MedalService(BaseService):
    """勋章管理服务"""

    def __init__(self, api: BiliApi, white_list: List[int], banned_list: List[int], logger=None):
        super().__init__(api, logger)
        self.white_list = white_list
        self.banned_list = banned_list

    async def get_all_medals(self, show_logs: bool = True) -> List[Dict[str, Any]]:
        """获取所有勋章"""
        medals = []
        filtered_count = 0
        whitelist_count = 0

        async for medal in self.api.getFansMedalandRoomID():
            target_id = safe_get(medal, 'medal', 'target_id')
            room_id = safe_get(medal, 'room_info', 'room_id')
            anchor_name = safe_get(medal, 'anchor_info',
                                   'nick_name', default='未知用户')

            # 必须有直播间
            if room_id == 0:
                continue

            # 黑名单模式
            if self.white_list == [0]:
                if target_id in self.banned_list:
                    if show_logs:
                        self.log.warning(f"{anchor_name} 在黑名单中，已过滤")
                    filtered_count += 1
                    continue
                medals.append(medal)
            else:
                # 白名单模式
                if target_id in self.white_list:
                    if show_logs:
                        self.log.success(f"{anchor_name} 在白名单中，加入任务")
                    medals.append(medal)
                    whitelist_count += 1

        return medals

    def _should_include_medal(self, medal: Dict[str, Any]) -> bool:
        """判断是否应该包含该勋章"""
        target_id = safe_get(medal, 'medal', 'target_id')
        room_id = safe_get(medal, 'room_info', 'room_id')

        # 必须有直播间
        if room_id == 0:
            return False

        # 黑名单模式
        if self.white_list == [0]:
            if target_id in self.banned_list:
                return False
            return True

        # 白名单模式
        if target_id in self.white_list:
            return True

        return False

    def classify_medals(self, medals: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """分类勋章"""
        classified = {
            'need_do': [],      # 需要做任务的勋章
            'others': [],       # 其他勋章
            'living': [],       # 开播中的勋章
            'no_living': []     # 未开播的勋章
        }

        for medal in medals:
            medal_data = safe_get(medal, 'medal', default={})
            room_status = safe_get(
                medal, 'room_info', 'living_status', default=0)
            medal_lighted = medal_data.get("is_lighted", 0)
            level = medal_data.get('level', 0)
            today_feed = medal_data.get('today_feed', 0)

            # 勋章点亮分类
            if medal_lighted == 0:
                if room_status == 1:
                    classified['living'].append(medal)
                else:
                    classified['no_living'].append(medal)

            # 任务分类
            if today_feed < 30:
                classified['need_do'].append(medal)
            else:
                classified['others'].append(medal)

        return classified

    async def execute(self, show_logs: bool = True, *args, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """执行勋章获取和分类"""
        medals = await self.get_all_medals(show_logs)
        return self.classify_medals(medals)


class LikeService(BaseService):
    """点赞服务"""

    async def like_medals(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
        """点赞勋章"""
        if config.get('LIKE_CD', 0) == 0:
            self.log.info("点赞任务已关闭")
            return True

        try:
            if not config.get('ASYNC', 0):
                await self._sync_like(medals, config)
            else:
                await self._async_like(medals, config)

            return True
        except Exception as e:
            self.log.exception("点赞任务异常")
            raise BiliException(f"点赞任务异常: {e}")

    async def _sync_like(self, medals: List[Dict[str, Any]], config: Dict[str, Any]):
        """同步点赞"""
        self.log.info("同步点赞任务开始....")

        for index, medal in enumerate(medals):
            for i in range(BiliConstants.Tasks.LIKE_COUNT_SYNC):
                if config.get('LIKE_CD'):
                    await self.api.likeInteractV3(
                        medal['room_info']['room_id'],
                        medal['medal']['target_id'],
                        self.api.u.mid
                    )
                await asyncio.sleep(config.get('LIKE_CD', 1))

            self.log.success(
                f"{medal['anchor_info']['nick_name']} 点赞{i+1}次成功 "
                f"{index+1}/{len(medals)}"
            )

    async def _async_like(self, medals: List[Dict[str, Any]], config: Dict[str, Any]):
        """异步点赞"""
        self.log.info("异步点赞任务开始....")

        for i in range(BiliConstants.Tasks.LIKE_COUNT_ASYNC):
            if config.get('LIKE_CD'):
                tasks = [
                    self.api.likeInteractV3(
                        medal['room_info']['room_id'],
                        medal['medal']['target_id'],
                        self.api.u.mid
                    )
                    for medal in medals
                ]
                await asyncio.gather(*tasks)

            self.log.success(f"异步点赞第{i+1}次成功")
            await asyncio.sleep(config.get('LIKE_CD', 1))

    async def execute(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
        """执行点赞任务"""
        return await self.like_medals(medals, config)


class DanmakuService(BaseService):
    """弹幕服务"""

    async def send_danmaku_to_medals(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> int:
        """向勋章发送弹幕"""
        if not config.get('DANMAKU_CD'):
            self.log.info("弹幕任务关闭")
            return 0

        estimated_time = (
            len(medals) *
            config.get('DANMAKU_CD', 3) *
            config.get('DANMAKU_NUM', 10)
        )
        self.log.info(f"弹幕打卡任务开始....(预计 {estimated_time} 秒完成)")

        success_count = 0

        for n, medal in enumerate(medals, 1):
            if config.get('WEARMEDAL'):
                await self.api.wearMedal(medal['medal']['medal_id'])
                await asyncio.sleep(0.5)

            anchor_name = medal['anchor_info']['nick_name']
            room_id = medal['room_info']['room_id']

            for i in range(config.get('DANMAKU_NUM', 10)):
                try:
                    ret_msg = await self.api.sendDanmaku(room_id)
                    self.log.debug(f"{anchor_name}: {ret_msg}")

                    if "重复弹幕" in ret_msg:
                        self.log.warning(f"{anchor_name}: 重复弹幕, 跳过后续弹幕")
                        break

                    await asyncio.sleep(config.get('DANMAKU_CD', 3))

                except Exception as e:
                    self.log.error(f"{anchor_name} 弹幕发送失败: {e}")
                    break
            else:
                success_count += 1
                self.log.success(f"{anchor_name} 弹幕打卡成功 {n}/{len(medals)}")

        return success_count

    async def execute(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> int:
        """执行弹幕任务"""
        return await self.send_danmaku_to_medals(medals, config)


class HeartbeatService(BaseService):
    """心跳观看服务"""

    async def watch_medals(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
        """观看直播间发送心跳"""
        watch_time = config.get('WATCHINGLIVE', 0)
        if not watch_time:
            self.log.info("每日观看直播任务关闭")
            return True

        self.log.info(f"每日{watch_time}分钟任务开始")
        self.log.info(f"预计共需运行{watch_time * len(medals)}分钟（{len(medals)}个勋章）")

        # 顺序执行所有勋章的心跳任务
        for index, medal in enumerate(medals, 1):
            await self._watch_single_medal(medal, watch_time, index, len(medals))

        self.log.success(f"每日{watch_time}分钟任务完成")
        return True

    async def _watch_single_medal(self, medal: Dict[str, Any], watch_time: int, index: int, total: int):
        """观看单个勋章的直播间"""
        anchor_name = medal['anchor_info']['nick_name']
        room_id = medal['room_info']['room_id']
        target_id = medal['medal']['target_id']

        self.log.info(
            f"开始观看 {anchor_name} 的直播间（{watch_time}分钟）- {index}/{total}")

        for minute in range(1, watch_time + 1):
            try:
                await self.api.heartbeat(room_id, target_id)

                if minute % 5 == 0:
                    self.log.success(
                        f"{anchor_name} 观看了 {minute} 分钟 ({index}/{total})")

                await asyncio.sleep(60)  # 每分钟发送一次

            except Exception as e:
                self.log.error(f"{anchor_name} 心跳发送失败: {e}")
                break

        self.log.success(f"{anchor_name} 观看任务完成 ({index}/{total})")

    async def execute(self, medals: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
        """执行观看任务"""
        return await self.watch_medals(medals, config)


class GroupService(BaseService):
    """应援团服务"""

    async def sign_in_groups(self, config: Dict[str, Any]) -> int:
        """应援团签到"""
        if not config.get('SIGNINGROUP'):
            self.log.info("应援团签到任务关闭")
            return 0

        self.log.info("应援团签到任务开始")
        success_count = 0

        try:
            async for group in self.api.getGroups():
                if group['owner_uid'] == self.api.u.mid:
                    continue

                try:
                    await self.api.signInGroups(group['group_id'], group['owner_uid'])
                    self.log.success(f"{group['group_name']} 签到成功")
                    success_count += 1
                    await asyncio.sleep(config.get('SIGNINGROUP', 2))

                except Exception as e:
                    self.log.error(f"{group['group_name']} 签到失败: {e}")
                    continue

        except KeyError as e:
            # 没有应援团时静默处理
            if str(e) != "'list'":
                self.log.error(f"获取应援团列表失败: {e}")
        except Exception as e:
            self.log.error(f"获取应援团列表失败: {e}")

        if success_count:
            self.log.success(f"应援团签到任务完成 {success_count}个")

        return success_count

    async def execute(self, config: Dict[str, Any]) -> int:
        """执行应援团签到"""
        return await self.sign_in_groups(config)


class CoinService(BaseService):
    """投币服务"""

    def __init__(self, api: BiliApi, white_list: List[int], banned_list: List[int], logger=None):
        super().__init__(api, logger)
        self.white_list = white_list
        self.banned_list = banned_list

    async def coin_videos(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """视频投币任务"""
        # 检查是否配置了投币目标
        coin_uid_config = config.get('coin_uid', 0)
        if not coin_uid_config or coin_uid_config == 0:
            self.log.info("未配置投币目标UP主，跳过投币任务")
            return {"success_count": 0, "total_coins": 0, "up_stats": {}}

        coin_remain = config.get('coin_remain', 0)
        coin_max = config.get('coin_max', 0)
        coin_max_per_uid = config.get('coin_max_per_uid', 0)

        try:
            # 获取用户信息和硬币数
            user_info = await self.api.getMyInfo()
            total_coins = user_info.get("coins", 0)

            self.log.info(f"当前硬币数: {total_coins}")

            # 检查硬币余额
            if total_coins <= coin_remain:
                self.log.info(f"硬币余额不足，当前: {total_coins}, 保留: {coin_remain}")
                return {"success_count": 0, "total_coins": total_coins, "up_stats": {}}

            # 计算可投币数
            available_coins = total_coins - coin_remain
            if coin_max > 0:
                max_coins = min(available_coins, coin_max)
            else:
                max_coins = available_coins

            if max_coins <= 0:
                self.log.info("当前无可用硬币")
                return {"success_count": 0, "total_coins": total_coins, "up_stats": {}}

            self.log.info(f"开始投币任务，可投币数: {max_coins}")

            # 获取视频列表
            videos = await self._get_videos_for_coin(config)
            if not videos:
                self.log.warning("未找到可投币的视频")
                return {"success_count": 0, "total_coins": total_coins, "up_stats": {}}

            # 执行投币
            success_count, up_stats = await self._coin_videos(videos, max_coins, coin_max_per_uid)

            self.log.success(f"投币任务完成，成功投币 {success_count} 次")
            return {"success_count": success_count, "total_coins": total_coins - success_count, "up_stats": up_stats}

        except Exception as e:
            self.log.error(f"投币任务异常: {e}")
            return {"success_count": 0, "total_coins": 0, "up_stats": {}}

    async def _get_videos_for_coin(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取可投币的视频列表"""
        videos = []
        coin_max_per_uid = config.get('coin_max_per_uid', 0)

        # 获取投币目标UP主列表
        target_uids = self._get_coin_target_uids(config)

        if target_uids:
            # 指定UP主投币，按顺序处理
            for uid in target_uids:
                try:
                    # 分页获取视频，直到找到足够的可投币视频或没有更多视频
                    up_videos, up_name = await self._get_videos_from_uid(uid, coin_max_per_uid)

                    if up_videos:
                        # 为每个视频添加UP主标识和名字，用于后续统计
                        for video in up_videos:
                            video["_coin_uid"] = uid
                            video["_coin_up_name"] = up_name

                        videos.extend(up_videos)
                        self.log.info(
                            f"获取到UP主 {up_name} ({uid}) 的 {len(up_videos)} 个可投币视频")
                    else:
                        self.log.warning(f"UP主 {up_name} ({uid}) 没有找到可投币的视频")
                except Exception as e:
                    self.log.error(f"获取UP主 {uid} 视频失败: {e}")
                    continue

            if videos:
                self.log.info(f"共获取到 {len(videos)} 个可投币视频，按UP主顺序排列")
        else:
            self.log.info("未指定投币UP主，跳过投币任务")

        return videos

    async def _get_videos_from_uid(self, uid: int, coin_max_per_uid: int) -> tuple[List[Dict[str, Any]], str]:
        """从指定UP主获取可投币视频，支持分页查询"""
        target_count = coin_max_per_uid if coin_max_per_uid > 0 else 5
        max_pages = 5  # 最多查询5页，避免无限查询
        ps = 20  # 每页获取20个视频

        all_videos = []
        available_videos = []
        last_aid = None
        page = 0
        up_name = f"UP主_{uid}"  # 默认名字

        # 先尝试获取一页视频来解析UP主名字
        try:
            first_result = await self.api.getUserVideoUploaded(uid, ps=10, order="pubdate")
            if first_result.get("item") and first_result["item"]:
                # 遍历视频列表，找到不包含"联合创作"的UP主名字
                for video in first_result["item"]:
                    if video.get("author") and "联合创作" not in video["author"]:
                        up_name = video["author"]
                        break
        except Exception as e:
            self.log.debug(f"获取UP主 {uid} 名字失败: {e}")

        while len(available_videos) < target_count and page < max_pages:
            page += 1
            try:
                # 分页获取视频
                result = await self.api.getUserVideoUploaded(uid, aid=last_aid, ps=ps, order="pubdate")

                if not result.get("item"):
                    self.log.debug(f"UP主 {up_name} ({uid}) 第{page}页没有更多视频")
                    break

                page_videos = result["item"]
                if not page_videos:
                    break

                # 更新分页参数
                last_aid = page_videos[-1].get(
                    "param") or page_videos[-1].get("aid")

                # 检查每个视频是否可投币
                for video in page_videos:
                    aid = video.get("param") or video.get("aid")
                    if not aid:
                        continue

                    try:
                        aid = int(aid)
                        # 检查是否已投币
                        coin_status = await self.api.getVideoCoinsStatus(aid=aid)
                        already_coined = coin_status.get("multiply", 0)

                        if already_coined < 2:  # 还可以投币
                            available_videos.append(video)
                            if len(available_videos) >= target_count:
                                break

                    except Exception as e:
                        self.log.debug(f"检查视频 av{aid} 投币状态失败: {e}")
                        continue

                # 短暂延迟，避免请求过快
                await asyncio.sleep(0.5)

            except Exception as e:
                self.log.error(f"获取UP主 {up_name} ({uid}) 第{page}页视频失败: {e}")
                break

        if page > 1:
            self.log.info(
                f"UP主 {up_name} ({uid}) 查询了 {page} 页，找到 {len(available_videos)} 个可投币视频")

        return available_videos[:target_count], up_name

    def _get_coin_target_uids(self, config: Dict[str, Any]) -> List[int]:
        """获取投币目标UP主列表，参考其他服务的黑白名单逻辑"""
        coin_uid_config = config.get('coin_uid', 0)
        coin_uids = self._parse_coin_uids(coin_uid_config)

        if not coin_uids:
            return []

        # 过滤UID：参考MedalService的逻辑
        target_uids = []

        # 黑名单模式
        if self.white_list == [0]:
            for uid in coin_uids:
                if uid not in self.banned_list:
                    target_uids.append(uid)
                else:
                    self.log.warning(f"UP主 {uid} 在黑名单中，已过滤")
        else:
            # 白名单模式：只有在白名单中的UID才能投币
            for uid in coin_uids:
                if uid in self.white_list:
                    target_uids.append(uid)
                    self.log.info(f"UP主 {uid} 在白名单中，加入投币任务")
                else:
                    self.log.warning(f"UP主 {uid} 不在白名单中，已过滤")

        return target_uids

    def _parse_coin_uids(self, coin_uid_config) -> List[int]:
        """解析投币UP主ID配置"""
        if not coin_uid_config:
            return []

        try:
            # 如果是数字，转换为字符串处理
            if isinstance(coin_uid_config, (int, float)):
                if coin_uid_config == 0:
                    return []
                return [int(coin_uid_config)]

            # 如果是字符串，按逗号分割
            if isinstance(coin_uid_config, str):
                uid_strs = coin_uid_config.strip().split(',')
                uids = []
                for uid_str in uid_strs:
                    uid_str = uid_str.strip()
                    if uid_str and uid_str != '0':
                        try:
                            uids.append(int(uid_str))
                        except ValueError:
                            self.log.warning(f"无效的UP主ID: {uid_str}")
                            continue
                return uids

            return []

        except Exception as e:
            self.log.error(f"解析投币UP主ID配置失败: {e}")
            return []

    async def _coin_videos(self, videos: List[Dict[str, Any]], max_coins: int, coin_max_per_uid: int = 0) -> tuple[int, Dict[int, Dict[str, Any]]]:
        """为视频投币"""
        success_count = 0
        uid_coin_count = {}  # 记录每个UP主已投币数
        up_stats = {}  # 记录UP主统计信息（包含名字）

        # 按UP主分组视频，避免重复检查已达上限的UP主
        videos_by_uid = {}
        for video in videos:
            uid = video.get("_coin_uid", 0)
            if uid not in videos_by_uid:
                videos_by_uid[uid] = []
            videos_by_uid[uid].append(video)

        # 按UP主处理视频
        for uid, up_videos in videos_by_uid.items():
            if success_count >= max_coins:
                break

            # 获取UP主信息
            up_name = up_videos[0].get(
                "_coin_up_name", f"UP主_{uid}") if up_videos else f"UP主_{uid}"

            # 处理该UP主的视频
            for video in up_videos:
                if success_count >= max_coins:
                    break

                # 检查单个UP主投币上限
                if coin_max_per_uid > 0 and uid > 0:
                    current_uid_coins = uid_coin_count.get(uid, 0)
                    if current_uid_coins >= coin_max_per_uid:
                        self.log.debug(
                            f"UP主 {up_name} ({uid}) 今日投币已达上限 {coin_max_per_uid}，跳过后续视频")
                        break  # 跳出该UP主的视频循环，不再处理该UP主的其他视频

                aid = video.get("param") or video.get("aid")
                # 解析视频标题
                video_title = video.get("title", "未知标题")

                if not aid:
                    continue

                try:
                    aid = int(aid)

                    # 检查是否已投币
                    coin_status = await self.api.getVideoCoinsStatus(aid=aid)
                    already_coined = coin_status.get("multiply", 0)

                    if already_coined >= 2:
                        self.log.debug(
                            f"视频 {video_title} (UP主: {up_name}) 已投满币，跳过")
                        continue

                    # 投币
                    coins_to_add = min(2 - already_coined,
                                       max_coins - success_count)

                    # 如果设置了单个UP主上限，还需要考虑该UP主的剩余投币数
                    if coin_max_per_uid > 0 and uid > 0:
                        current_uid_coins = uid_coin_count.get(uid, 0)
                        uid_remaining = coin_max_per_uid - current_uid_coins
                        coins_to_add = min(coins_to_add, uid_remaining)

                    if coins_to_add <= 0:
                        continue

                    await self.api.coinVideo(aid, multiply=coins_to_add, select_like=0)

                    success_count += coins_to_add
                    if uid > 0:
                        uid_coin_count[uid] = uid_coin_count.get(
                            uid, 0) + coins_to_add

                        # 更新UP主统计信息
                        if uid not in up_stats:
                            up_stats[uid] = {"count": 0, "name": up_name}
                        up_stats[uid]["count"] += coins_to_add

                    self.log.success(
                        f"为视频 {video_title} (UP主: {up_name}) 投币 {coins_to_add} 个")

                    # 投币间隔
                    await asyncio.sleep(3)

                except Exception as e:
                    self.log.error(f"为视频 av{aid} 投币失败: {e}")
                    continue

        # 输出每个UP主的投币统计
        if uid_coin_count:
            for uid, count in uid_coin_count.items():
                up_name = up_stats.get(uid, {}).get("name", f"UP主_{uid}")
                self.log.info(f"UP主 {up_name} ({uid}) 本次投币 {count} 个")

        return success_count, up_stats

    async def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """执行投币任务"""
        return await self.coin_videos(config)
