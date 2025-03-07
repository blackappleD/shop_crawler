"""Cookie更新模块"""
import traceback
from loguru import logger
from typing import Dict, List, Any
from playwright.async_api import async_playwright
from ck.jd import *
from ck.jd.captcha_crack_pc import get_jd_cookie_pc
from utils.db_manager import RedisManager, MysqlManager
from utils.jd_ck import get_invalid_ck_ids
from utils.tools import (
    get_forbidden_users_dict,
    filter_forbidden_users,
    send_msg,
    desensitize_account
)
from api.send import SendApi
from config import (
    user_datas,
    account_source,
    cookie_source,
    cookie_target,
    mysql_config,
    redis_config
)

# 尝试从config导入enable_desensitize，如果不存在则默认为False
try:
    from config import enable_desensitize
except ImportError:
    enable_desensitize = False

# 初始化发送API
send_api = SendApi("cookie_updater")


async def get_account(mysql_manager: MysqlManager) -> Dict[str, Any]:
    """获取用户数据"""
    if account_source == "config":
        # 使用配置文件中的用户数据
        return user_datas
    elif account_source == "mysql" and mysql_manager:
        # 从MySQL获取用户数据
        user_data_dict = {}
        accounts = mysql_manager.get_all_accounts()
        for account in accounts:
            username = account.get("username")
            user_data_dict[username] = {
                "password": account.get("password"),
                "pin": username,  # 使用username作为pin
                "phone": account.get("phone"),
                "sms_func": "manual_input",  # 使用默认的短信验证方式
            }
        return user_data_dict
    return {}


async def get_cookies_data(redis_manager: RedisManager) -> tuple[List[Dict[str, Any]], bool]:
    """获取Cookie数据"""
    jd_ck_env_datas = []
    update_all_accounts = False
    if cookie_source == "redis" and redis_manager:
        # 从Redis获取Cookie
        logger.info("从Redis获取Cookie")
        all_cookie_redis = redis_manager.get_all_cookies()
        logger.info(f"从Redis获取到的Cookie数据类型: {type(all_cookie_redis)}, 值: {all_cookie_redis}")

        # 检查Redis中是否有Cookie数据
        if all_cookie_redis is None or (isinstance(all_cookie_redis, dict) and len(all_cookie_redis) == 0):
            logger.info("Redis中的JD_COOKIE_MAP为空或不存在，将更新所有账号的Cookie")
            update_all_accounts = True
        else:
            logger.info(f"Redis中的JD_COOKIE_MAP包含 {len(all_cookie_redis)} 个账号的Cookie")

        if all_cookie_redis:
            for username, cookie in all_cookie_redis.items():
                jd_ck_env_datas.append({
                    'id': username,  # 使用username作为ID
                    'value': cookie,
                    'status': 0,  # 默认启用状态
                    'name': 'JD_COOKIE',
                    'remarks': f'用户: {username}'
                })

    return jd_ck_env_datas, update_all_accounts


async def check_cookies(ck_datas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """检查Cookie有效性"""
    try:
        logger.info("检测CK任务开始")
        # 这一步会去检测这些JD_COOKIE
        invalid_cks_id_list = await get_invalid_ck_ids(ck_datas)
        if invalid_cks_id_list:
            # 更新jd_ck_env_datas中失效CK的状态
            ck_datas = [
                {**x, 'status': 1} if x.get('id') in invalid_cks_id_list or x.get('_id') in invalid_cks_id_list else x
                for x in ck_datas]
        logger.info("检测CK任务完成")
        return ck_datas
    except Exception as e:
        logger.error(f"检测CK任务失败, 跳过检测, 报错原因为{e}")
        return ck_datas


async def get_update_users(jd_ck_env_datas: List[Dict[str, Any]], user_data_dict: Dict[str, Any],
                           update_all_accounts: bool) -> Dict[str, Any]:
    """获取需要更新的用户"""
    if update_all_accounts:
        logger.info("即将更新所有账号的Cookie")
        user_dict = {}
        for username, user_data in user_data_dict.items():
            user_dict[username] = {
                'id': username,
                'value': '',  # 空值，稍后会在更新时填充
                'name': 'JD_COOKIE',
                'remarks': f'用户: {username}'
            }
        return user_dict

    # 获取需强制更新pin
    force_update_pins = [user_data_dict[key]["pin"] for key in user_data_dict if
                         user_data_dict[key].get("force_update") is True]
    # 获取禁用和需要强制更新的users
    forbidden_users = [x for x in jd_ck_env_datas if (x['status'] == 1 or x.get('pin') in force_update_pins)]

    if not forbidden_users:
        logger.info("所有COOKIE环境变量正常，无需更新")
        return {}

    # 获取需要的字段
    filter_users_list = filter_forbidden_users(forbidden_users, ['_id', 'id', 'value', 'remarks', 'name'])

    # 生成字典
    user_dict = get_forbidden_users_dict(filter_users_list, user_data_dict)
    if not user_dict:
        logger.info("失效的CK信息未配置在user_datas内，无需更新")

    return user_dict


async def update_cookie(user: str, user_dict: Dict[str, Any], user_data_dict: Dict[str, Any],
                        redis_manager: RedisManager, mode: str) -> bool:
    """更新单个用户的Cookie"""
    # from main import get_jd_cookie_pc  # 避免循环导入

    logger.info(f"开始更新{desensitize_account(user, enable_desensitize)}")

    # 登录JD获取cookie
    async with async_playwright() as playwright:
        new_cookie = await get_jd_cookie_pc(playwright, user, user_data_dict, mode)

    if new_cookie is None:
        logger.error(f"获取cookie失败")
        await send_msg(send_api, send_type=1, msg=f"{desensitize_account(user, enable_desensitize)} 更新失败")
        return False

    req_data = user_dict[user]
    # 更新为新的完整cookie字符串
    req_data["value"] = new_cookie
    logger.info(f"更新内容为{req_data}")

    if cookie_target == "redis" and redis_manager:
        # 更新Redis中的Cookie
        if not redis_manager.set_cookie(user, new_cookie):
            logger.error(f"{desensitize_account(user, enable_desensitize)}更新失败")
            await send_msg(send_api, send_type=1, msg=f"{desensitize_account(user, enable_desensitize)} 更新失败")
            return False

    logger.info(f"{desensitize_account(user, enable_desensitize)}更新成功")
    await send_msg(send_api, send_type=0, msg=f"{desensitize_account(user, enable_desensitize)} 更新成功")
    return True


async def run_update(mode, redis_manager, mysql_manager):
    """运行更新任务
    
    Args:
        mode: 运行模式, 当mode = cron时，sms_func为 manual_input时，将自动传成no
        :param mode:
        :param mysql_manager:
        :param redis_manager:
    """
    try:

        # 2. 获取用户数据
        user_account_dict = await get_account(mysql_manager)

        # 3. 获取Cookie数据
        ck_datas, update_all_accounts = await get_cookies_data(redis_manager)

        # 4. 检查Cookie有效性（如果不是更新所有账号）
        if not update_all_accounts:
            ck_datas = await check_cookies(ck_datas)

        # 5. 获取需要更新的用户
        user_dict = await get_update_users(ck_datas, user_account_dict, update_all_accounts)
        if not user_dict:
            # 关闭MySQL连接
            if mysql_manager:
                mysql_manager.close()
            return

        # 6. 更新Cookie
        for user in user_dict:
            await update_cookie(user, user_dict, user_account_dict, redis_manager, mode)

        # 7. 关闭MySQL连接
        if mysql_manager:
            mysql_manager.close()

    except Exception as e:
        logger.error(f"更新任务执行出错: {e}")
        logger.error(traceback.format_exc())
