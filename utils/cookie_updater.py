"""Cookie更新模块"""
import traceback
from loguru import logger
from typing import Dict, List, Any
from playwright.async_api import async_playwright
from jd.ck.captcha_crack_pc import get_jd_cookie_pc
from jd.ck.cookie_checker_pc import get_need_login_usernames
from utils.consts import Account
from utils.db_manager import RedisManager, MysqlManager
from utils.tools import (
    send_msg,
    desensitize_account
)
from utils import consts
from api.send import SendApi
from config import (
    account_source,
    cookie_source,
    cookie_target,
)

# 尝试从config导入enable_desensitize，如果不存在则默认为False
try:
    from config import enable_desensitize
except ImportError:
    enable_desensitize = False

# 初始化发送API
send_api = SendApi("cookie_updater")


async def get_account(mysql_manager: MysqlManager, enterprise) -> List[Account]:
    """获取用户数据，返回Account对象列表"""
    if account_source == "mysql" and mysql_manager:
        # 从MySQL获取用户数据
        result = mysql_manager.get_all_accounts(enterprise)

        # 处理MySQL查询结果为Account对象列表
        accounts_list = []
        for account_data in result:
            username = account_data.get('username')
            if username:
                account = Account(
                    username=username,
                    password=account_data.get('password'),
                    phone=account_data.get('phone'),
                    enable=account_data.get('enable'),
                    status=account_data.get('status'),
                    user_type=account_data.get('user_type'),
                    force_update=account_data.get('force_update'),
                    enterprise=account_data.get('enterprise'),
                    sms_func=account_data.get('sms_func'),
                    sms_webhook=account_data.get('sms_webhook'),
                    voice_func=account_data.get('voice_func'),
                    id=account_data.get('id')
                )
                accounts_list.append(account)

        logger.info(f"从MySQL获取到 {len(accounts_list)} 个账号")
        return accounts_list

    # 默认返回空列表
    logger.warning("未能从任何数据源获取账号信息")
    return []


async def get_cookies_data(redis_manager: RedisManager) -> tuple[List[Dict[str, Any]], bool]:
    """获取Cookie数据"""
    jd_ck_datas = []
    update_all_accounts = False
    if cookie_source == "redis" and redis_manager:
        # 从Redis获取Cookie
        # logger.info("从Redis获取Cookie")
        all_cookie_redis = redis_manager.get_all_cookies()
        # logger.info(f"从Redis获取到的Cookie数据类型: {type(all_cookie_redis)}, 值: {all_cookie_redis}")

        # 检查Redis中是否有Cookie数据
        if all_cookie_redis is None or (isinstance(all_cookie_redis, dict) and len(all_cookie_redis) == 0):
            logger.info("Redis中的COOKIE_MAP为空或不存在，将更新所有账号的Cookie")
            update_all_accounts = True
        else:
            logger.info(f"Redis中的COOKIE_MAP包含 {len(all_cookie_redis)} 个账号的Cookie")

        if all_cookie_redis:
            for username, cookie in all_cookie_redis.items():
                jd_ck_datas.append({
                    'username': username,
                    'cookie': cookie,
                })
    return jd_ck_datas, update_all_accounts


async def check_cookies(username_cookie_list):
    """检查Cookie有效性"""
    need_login_usernames = []
    try:
        logger.info("检测CK任务开始")
        need_login_usernames = await get_need_login_usernames(username_cookie_list)
        if need_login_usernames:
            logger.info("检测CK任务完成")
            return need_login_usernames
        else:
            return need_login_usernames
    except Exception as e:
        logger.error(f"检测CK任务失败, 跳过检测, 报错原因为{e}")
        return need_login_usernames


async def get_update_accounts(need_login_usernames, all_accounts: List[Account],
                              update_all_accounts: bool) -> List[Account]:
    """获取需要更新的用户"""
    if update_all_accounts:
        logger.info("即将更新所有账号的Cookie")
        return all_accounts

    # 获取需要登录的账号列表
    need_login_accounts = []
    for username in need_login_usernames:
        # 从all_accounts中找到对应的Account对象
        account = next((acc for acc in all_accounts if acc.username == username), None)
        if account:
            need_login_accounts.append(account)
        else:
            logger.warning(f"未找到用户名 {username} 对应的账号信息")

    # 获取需要强制更新的账号
    for account in all_accounts:
        if account.force_update:
            need_login_accounts.append(account)

    if not need_login_accounts:
        logger.info("所有Cookie环境变量正常，无需更新")
        return []

    return need_login_accounts


async def update_cookie(account, redis_manager: RedisManager, mysql_manager: MysqlManager, mode: str) -> bool:
    """更新单个用户的Cookie"""
    logger.info(f"开始更新{desensitize_account(account.username, enable_desensitize)}")

    # 登录JD获取cookie
    async with async_playwright() as playwright:
        new_cookie = await get_jd_cookie_pc(playwright, account, mysql_manager, mode)

    if new_cookie is None:
        logger.error(f"获取cookie失败")
        await send_msg(send_api, send_type=1,
                       msg=f"{desensitize_account(account.username, enable_desensitize)} 更新失败")
        return False
    logger.info(f"更新内容为{new_cookie}")
    if cookie_target == "redis" and redis_manager:
        # 更新Redis中的Cookie
        if not redis_manager.set_cookie(account.username, new_cookie):
            logger.error(f"{desensitize_account(account.username, enable_desensitize)}更新失败")
            await send_msg(send_api, send_type=1,
                           msg=f"{desensitize_account(account.username, enable_desensitize)} 更新失败")
            return False

    logger.info(f"{desensitize_account(account.username, enable_desensitize)}更新成功")
    await send_msg(send_api, send_type=0, msg=f"{desensitize_account(account.username, enable_desensitize)} 更新成功")
    return True


async def run_update(mode, redis_manager, mysql_manager):
    """运行更新任务
    
    Args:
        mode: 运行模式, 当mode = cron时，sms_func为 manual_input时，将自动传成no
        redis_manager: Redis管理器
        mysql_manager: MySQL管理器
    """
    try:
        # 1. 获取所有账号数据
        all_accounts = await get_account(mysql_manager, consts.Enterprise.all)
        logger.info(f"获取到 {len(all_accounts)} 个账号")

        # 2. 获取Cookie数据
        username_cookie_list, is_update_all_accounts = await get_cookies_data(redis_manager)

        # 3. 检查Cookie有效性（如果不是更新所有账号）
        need_login_usernames = []
        if not is_update_all_accounts:
            need_login_usernames = await check_cookies(username_cookie_list)

        # 4. 将accounts中存在但在username_cookie_map中不存在的用户名添加到need_login_accounts
        username_list = [item.get('username') for item in username_cookie_list]
        for account in all_accounts:
            if account.username not in username_list:
                logger.info(f"用户 {account.username} 在Cookie数据中不存在，添加到需要登录的账号列表")
                need_login_usernames.append(account.username)

        # 5. 获取需要更新的用户
        need_login_accounts = await get_update_accounts(need_login_usernames, all_accounts, is_update_all_accounts)
        if not need_login_accounts:
            logger.info("没有需要更新的账号")
            # 关闭MySQL连接
            if mysql_manager:
                mysql_manager.close()
            return
        logger.info(f"本次需要更新Cookie的账号数量为: {len(need_login_accounts)}")
        # 6. 更新Cookie
        for account in need_login_accounts:
            await update_cookie(account, redis_manager, mysql_manager, mode)

        # 7. 关闭MySQL连接
        if mysql_manager:
            mysql_manager.close()

    except Exception as e:
        logger.error(f"更新任务执行出错: {e}")
        logger.error(traceback.format_exc())
