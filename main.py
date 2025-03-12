import argparse
from loguru import logger
from utils.cookie_updater import (
    run_update
)

import uvicorn

from utils.db_manager import RedisManager, MysqlManager

logger.add(
    sink="main.log",
    level="DEBUG"
)

try:
    # 账号是否脱敏的开关
    from config import enable_desensitize
except ImportError:
    enable_desensitize = False

# 导入新增配置
try:
    from config import (
        mysql_config,
        redis_config,
        account_source,
        cookie_source,
        cookie_target,
        sms_func
    )
except ImportError:
    # 默认使用原有方式
    raise


async def init_data_sources():
    """初始化数据源连接"""
    redis_manager = None
    mysql_manager = None

    # 初始化Redis连接（如果需要）
    if cookie_source == "redis" or cookie_target == "redis":
        redis_manager = RedisManager(
            host=redis_config.get("host"),
            port=redis_config.get("port"),
            db=redis_config.get("db"),
            password=redis_config.get("password")
        )

    # 初始化MySQL连接（如果需要）
    if account_source == "mysql":
        mysql_manager = MysqlManager(
            host=mysql_config.get("host"),
            port=mysql_config.get("port"),
            user=mysql_config.get("user"),
            password=mysql_config.get("password"),
            database=mysql_config.get("database")
        )

    return redis_manager, mysql_manager


async def main(mode: str = None):
    redis_manager, mysql_manager = await init_data_sources()
    await run_update(mode, redis_manager, mysql_manager)


def parse_args():
    """解析参数"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mode', choices=['cron'], help="运行的main的模式(例如: 'cron')")
    parser.add_argument('-p', '--port', type=int, default=8080, help="服务运行的端口号")
    parser.add_argument('--host', default="127.0.0.1", help="服务运行的主机地址")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    # 启动FastAPI服务
    uvicorn.run(
        "app:app",  # 使用模块导入方式
        host=args.host,
        port=args.port,
        log_level="info"
    )
