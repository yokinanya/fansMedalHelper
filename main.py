import json
import os
import sys
from loguru import logger
import warnings
import asyncio
import aiohttp
import itertools
from src import BiliUser

log = logger.bind(user="B站粉丝牌助手")
__VERSION__ = "0.3.9-yokinanya"

warnings.filterwarnings(
    "ignore",
    message="The localize method is no longer necessary, as this time zone supports the fold attribute",
)
os.chdir(os.path.dirname(os.path.abspath(__file__)).split(__file__)[0])

try:
    if os.environ.get("USERS"):
        users = json.loads(os.environ.get("USERS"))
    else:
        import yaml

        with open("users.yaml", "r", encoding="utf-8") as f:
            users = yaml.load(f, Loader=yaml.FullLoader)
    assert users["ASYNC"] in [0, 1], "ASYNC参数错误"
    assert users["LIKE_CD"] >= 0, "LIKE_CD参数错误"
    # assert users['SHARE_CD'] >= 0, "SHARE_CD参数错误"
    assert users["DANMAKU_CD"] >= 0, "DANMAKU_CD参数错误"
    assert users["DANMAKU_NUM"] >= 0, "DANMAKU_NUM参数错误"
    assert users["WATCHINGLIVE"] >= 0, "WATCHINGLIVE参数错误"
    assert users["WEARMEDAL"] in [0, 1], "WEARMEDAL参数错误"
    assert users.get("WATCHINGALL", 0) in [0, 1], "WATCHINGALL参数错误"
    config = {
        "ASYNC": users["ASYNC"],
        "LIKE_CD": users["LIKE_CD"],
        # "SHARE_CD": users['SHARE_CD'],
        "DANMAKU_CD": users["DANMAKU_CD"],
        "DANMAKU_NUM": users.get("DANMAKU_NUM", 10),
        "WATCHINGLIVE": users["WATCHINGLIVE"],
        "WEARMEDAL": users["WEARMEDAL"],
        "SIGNINGROUP": users.get("SIGNINGROUP", 2),
        "PROXY": users.get("PROXY"),
        "WATCHINGALL": users.get("WATCHINGALL", 0),
    }
except Exception as e:
    log.error(f"读取配置文件失败,请检查配置文件格式是否正确: {e}")
    exit(1)


@log.catch
async def main():
    messageList = []
    session = aiohttp.ClientSession(trust_env=True)
    log.warning("当前版本为: " + __VERSION__)
    initTasks = []
    startTasks = []
    catchMsg = []
    for user in users["USERS"]:
        if user["access_key"]:
            biliUser = BiliUser(
                user["access_key"],
                user.get("white_uid", ""),
                user.get("banned_uid", ""),
                config,
            )
            initTasks.append(biliUser.init())
            startTasks.append(biliUser.start())
            catchMsg.append(biliUser.sendmsg())
    try:
        await asyncio.gather(*initTasks)
        await asyncio.gather(*startTasks)
    except Exception as e:
        log.exception(e)
        # messageList = messageList + list(itertools.chain.from_iterable(await asyncio.gather(*catchMsg)))
        messageList.append(f"任务执行失败: {e}")
    finally:
        messageList = messageList + list(
            itertools.chain.from_iterable(await asyncio.gather(*catchMsg))
        )
    [log.info(message) for message in messageList]
    if users.get("SENDKEY", ""):
        await push_message(session, users["SENDKEY"], "  \n".join(messageList))
    await session.close()
    if users.get("MOREPUSH", ""):
        from onepush import notify

        notifier = users["MOREPUSH"]["notifier"]
        params = users["MOREPUSH"]["params"]
        notify(
            notifier,
            title=f"【B站粉丝牌助手推送】",
            content="  \n".join(messageList),
            **params,
            proxy=config.get("PROXY"),
        )
        log.info(f"{notifier} 已推送")


def run(*args, **kwargs):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
    log.info("任务结束，等待下一次执行。")


async def push_message(session, sendkey, message):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": f"【B站粉丝牌助手推送】", "desp": message}
    await session.post(url, data=data)
    log.info("Server酱已推送")


if __name__ == "__main__":
    cron = users.get("CRON", None)

    if cron:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        log.info(f"使用内置定时器 {cron}，开启定时任务，等待时间到达后执行。")
        schedulers = BlockingScheduler()
        schedulers.add_job(run, CronTrigger.from_crontab(cron), misfire_grace_time=3600)
        schedulers.start()
    elif "--auto" in sys.argv:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        import datetime

        log.info("使用自动守护模式，每隔 24 小时运行一次。")
        scheduler = BlockingScheduler(timezone="Asia/Shanghai")
        scheduler.add_job(
            run,
            IntervalTrigger(hours=24),
            next_run_time=datetime.datetime.now(),
            misfire_grace_time=3600,
        )
        scheduler.start()
    else:
        log.info("未配置定时器，开启单次任务。")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        log.info("任务结束")
