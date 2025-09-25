"""
常量定义模块
"""
from typing import List


class BiliConstants:
    """B站相关常量"""

    # API相关
    APPKEY = "4409e2ce8ffd12b8"
    APPSECRET = "59b43e04ad6965f34319062b478f83dd"
    APPBUILD = "6731100"

    # Headers
    HEADERS = {
        "User-Agent": "Mozilla/5.0 BiliDroid/6.73.1 (bbcallen@gmail.com) os/android model/Mi 10 Pro mobi_app/android build/6731100 channel/xiaomi innerVer/6731110 osVer/12 network/2",
    }

    # 弹幕内容
    DANMAKU_LIST: List[str] = [
        "(⌒▽⌒).",
        "（￣▽￣）.",
        "(=・ω・=).",
        "(｀・ω・´).",
        "(〜￣△￣)〜.",
        "(･∀･).",
        "(°∀°)ﾉ.",
        "(￣3￣).",
        "╮(￣▽￣)╭.",
        "_(:3」∠)_.",
        "(^・ω・^ ).",
        "(●￣(ｴ)￣●).",
        "ε=ε=(ノ≧∇≦)ノ.",
        "⁄(⁄ ⁄•⁄ω⁄•⁄ ⁄)⁄.",
        "←◡←.",
    ]

    # API URLs
    class URLs:
        FANS_MEDAL_PANEL = "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/panel"
        LIKE_INTERACT = "https://api.live.bilibili.com/xlive/web-ucenter/v1/interact/likeInteract"
        LIKE_INTERACT_V3 = "https://api.live.bilibili.com/xlive/app-ucenter/v1/like_info_v3/like/likeReportV3"
        SHARE_ROOM = "https://api.live.bilibili.com/xlive/app-room/v1/index/TrigerInteract"
        SEND_DANMAKU = "https://api.live.bilibili.com/xlive/app-room/v1/dM/sendmsg"
        LOGIN_INFO = "https://api.bilibili.com/x/web-interface/nav"
        USER_INFO = "https://api.live.bilibili.com/xlive/web-ucenter/user/get_user_info"
        MEDALS_INFO = "https://api.live.bilibili.com/xlive/web-ucenter/v1/fansMedal/medal"
        HEARTBEAT = "https://live-trace.bilibili.com/xlive/data-interface/v1/heartbeat/mobileHeartBeat"
        WEAR_MEDAL = "https://api.live.bilibili.com/xlive/app-room/v1/fansMedal/wear"
        GROUPS = "https://api.vc.bilibili.com/link_group/v1/member/my_groups"
        SIGN_IN_GROUPS = "https://api.vc.bilibili.com/link_setting/v1/link_setting/sign_in"

        # 投币相关
        VIDEO_COINS_STATUS = "https://api.bilibili.com/x/web-interface/archive/coins"
        COIN_VIDEO = "https://app.bilibili.com/x/v2/view/coin/add"
        USER_VIDEOS = "https://app.biliapi.com/x/v2/space/archive/cursor"
        MY_INFO = "https://app.bilibili.com/x/v2/account/myinfo"

    # 错误码
    class ErrorCodes:
        SUCCESS = 0
        TOKEN_ERROR = 1011040
        RATE_LIMIT = 10030
        SERVER_ERROR = -504

    # 任务相关
    class Tasks:
        MAX_RETRY_TIMES = 10
        LIKE_COUNT_SYNC = 30
        LIKE_COUNT_ASYNC = 35
        HEARTBEAT_INTERVAL = 60  # 秒
        DEFAULT_PAGE_SIZE = 50
