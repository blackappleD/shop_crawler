from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from crawler import router as crawler_router
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

# 注册爬虫路由
app.include_router(crawler_router, prefix="/api/crawler", tags=["crawler"])

def get_next_runtime(cron_expression, base_time=None):
    base_time = base_time or datetime.now()
    cron = croniter(cron_expression, base_time)
    return cron.get_next(datetime)

async def schedule_task():
    """定时任务"""
    next_run = get_next_runtime(cron_expression)
    logger.info(f"下次更新任务时间为{next_run}")
    while True:
        now = datetime.now()
        if now >= next_run:
            await main(mode="cron")
            next_run = get_next_runtime(cron_expression, now + timedelta(seconds=1))
            logger.info(f"下次更新任务时间为{next_run}")
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    """启动时执行的事件"""
    # 启动定时任务
    asyncio.create_task(schedule_task()) 