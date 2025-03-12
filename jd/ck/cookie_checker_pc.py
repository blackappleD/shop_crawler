import asyncio
from enum import Enum
import random
from typing import Any, List, Dict
import aiohttp
from loguru import logger
from playwright.async_api import async_playwright

from config import headless_login


class CheckCkCode(Enum):
    not_login = 1001


async def check_ck_pc(jd_ck) -> dict[str, Any]:
    """
    检测JD_COOKIE是否失效，通过访问个人主页方式验证
    使用Playwright代替接口调用
    """
    username = jd_ck['username']
    cookie = jd_ck["cookie"]

    url = "https://home.jd.com/index.html"
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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
    }

    try:
        async with async_playwright() as p:
            # 使用无头浏览器模式
            browser = await p.chromium.launch(headless=headless_login)

            # 创建新的浏览器上下文
            context = await browser.new_context(
                user_agent=headers["user-agent"],
                extra_http_headers={k: v for k, v in headers.items() if k != "user-agent" and k != "Cookie"}
            )

            # 解析Cookie字符串并设置Cookie
            cookies = []
            for cookie_item in cookie.split(';'):
                if not cookie_item.strip():
                    continue
                parts = cookie_item.strip().split('=', 1)
                if len(parts) == 2:
                    name, value = parts
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.jd.com',
                        'path': '/'
                    })

            await context.add_cookies(cookies)

            # 创建新页面并访问
            page = await context.new_page()
            await page.goto(url)

            # 获取页面内容
            content = await page.content()

            # 关闭浏览器
            await browser.close()

            # 检查页面内容，查找是否需要登录的标识
            if "欢迎登录" in content:
                logger.warning(f"检测到失效Cookie: {username}")
                return {"code": str(CheckCkCode.not_login.value), "message": content}
            else:
                logger.info(f"检测到Cookie尚未失效: {username}")
                return {"code": "0", "message": "已登录"}
    except Exception as e:
        logger.error(f"检测JD Cookie失效异常: {e}")
        # 发生异常时，保守起见，返回未登录状态
        return {"code": str(CheckCkCode.not_login.value), "message": f"检测异常: {str(e)}"}

    # 检测这里太快了, sleep一会儿, 避免FK
    finally:
        await asyncio.sleep(random.uniform(0.5, 2))


async def get_need_login_usernames(jd_ck_list: list):
    """
    传入CK列表，过滤失效CK列表
    """
    usernames = []
    for jd_ck in jd_ck_list:
        r = await check_ck_pc(jd_ck)
        if r.get('code') == str(CheckCkCode.not_login.value):
            usernames.append(jd_ck["username"])
    return usernames
