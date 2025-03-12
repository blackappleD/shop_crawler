from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from api.api_handler import router as api_router
from datetime import datetime, timedelta
from croniter import croniter
from config import cron_expression
from loguru import logger
from main import main

app = FastAPI(title="Shop Crawler API")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix="/api", tags=["api"])

# 全局变量，用于控制定时任务
scheduler_task = None


def get_next_runtime(cron_expression, base_time=None):
    """获取下一次运行时间，使用本地时区"""
    # 如果没有提供基准时间，使用当前时间
    base_time = base_time or datetime.now()
    # 确保使用本地时区
    if base_time.tzinfo is None:
        base_time = base_time.astimezone()
    cron = croniter(cron_expression, base_time)
    next_time = cron.get_next(datetime)
    # 确保返回的时间也是本地时区的
    if next_time.tzinfo is None:
        next_time = next_time.astimezone()
    return next_time


async def schedule_task():
    """定时任务"""
    try:
        logger.info("定时任务启动")
        next_run = get_next_runtime(cron_expression)
        logger.info(f"下次更新任务时间为 {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        while True:
            try:
                now = datetime.now().astimezone()
                logger.debug(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

                if now >= next_run:
                    logger.info(f"开始执行定时更新任务，当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    await main(mode="cron")
                    logger.info("定时更新任务执行完成")

                    # 计算下次运行时间
                    next_run = get_next_runtime(cron_expression, now + timedelta(seconds=1))
                    logger.info(f"下次更新任务时间为 {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")

                # 计算到下次执行的等待时间
                wait_seconds = (next_run - now).total_seconds()
                # 如果等待时间大于60秒，就等待60秒后再检查
                # 如果等待时间小于60秒，就等待实际的时间
                sleep_time = min(max(wait_seconds, 1), 60)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"定时任务执行出错: {e}")
                # 出错后等待60秒再继续
                await asyncio.sleep(60)
                continue

    except Exception as e:
        logger.error(f"定时任务异常退出: {e}")
    finally:
        logger.info("定时任务结束")


@app.on_event("startup")
async def startup_event():
    """启动时执行的事件"""
    global scheduler_task
    # 启动定时任务
    scheduler_task = asyncio.create_task(schedule_task())
    logger.info("应用启动，定时任务已创建")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时执行的事件"""
    global scheduler_task
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("应用关闭，定时任务已取消")
