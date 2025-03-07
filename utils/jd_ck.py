import asyncio
from enum import Enum
import json
import random
from utils.tools import send_request
from typing import List, Any
import aiohttp
from loguru import logger


class CheckCkCode(Enum):
    not_login = 1001


# async def check_ck_mobile(
#         cookie: str
# ) -> dict[str, Any]:
#     """
#     检测JD_COOKIE是否失效
#
#     :param cookie: 就是cookie
#     """
#
#     url = "https://me-api.jd.com/user_new/info/GetJDUserInfoUnion"
#     method = 'get'
#     headers = {
#         "Host": "me-api.jd.com",
#         "Accept": "*/*",
#         "Connection": "keep-alive",
#         "Cookie": cookie,
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.42",
#         "Accept-Language": "zh-cn",
#         "Referer": "https://home.m.jd.com/myJd/newhome.action?sceneval=2&ufc=&",
#         "Accept-Encoding": "gzip, deflate, br"
#     }
#     r = await send_request(url, method, headers)
#     # 检测这里太快了, sleep一会儿, 避免FK
#     await asyncio.sleep(random.uniform(0.5, 2))
#     return r

async def check_ck_pc(
        cookie: str
) -> dict[str, Any]:
    """
    检测JD_COOKIE是否失效，通过访问个人主页方式验证
    """
    url = "https://home.jd.com/index.html"
    method = 'get'
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,en-GB;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
        "Cookie": cookie
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url=url, headers=headers) as response:
                content = await response.text()
                
                # 检查页面内容，查找是否需要登录的标识
                if "请登录" in content or "登录京东" in content:
                    return {"retcode": str(CheckCkCode.not_login.value), "message": "未登录"}
                else:
                    return {"retcode": "0", "message": "已登录"}
    except Exception as e:
        logger.error(f"检测JD Cookie失效异常: {e}")
        # 发生异常时，保守起见，返回未登录状态
        return {"retcode": str(CheckCkCode.not_login.value), "message": f"检测异常: {str(e)}"}
    
    # 检测这里太快了, sleep一会儿, 避免FK
    finally:
        await asyncio.sleep(random.uniform(0.5, 2))


async def get_invalid_cks(
        jd_ck_list: list
) -> List[dict]:
    """
    传入CK列表，过滤失效CK列表
    """
    ck_list = []
    for jd_ck in jd_ck_list:
        cookie = jd_ck['value']
        r = await check_ck_pc(cookie)
        if r.get('retcode') == str(CheckCkCode.not_login.value):
            ck_list.append(jd_ck)

    return ck_list


async def get_invalid_ck_ids(cks):
    # 检测CK是否失效
    invalid_cks_list = await get_invalid_cks(cks)

    invalid_cks_id_list = [ck['id'] if 'id' in ck.keys() else ck["_id"] for ck in invalid_cks_list]
    return invalid_cks_id_list
