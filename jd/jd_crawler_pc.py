import asyncio
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from loguru import logger
from playwright_stealth import stealth_async
from config import headless_crawler
from crawler.base_crawler import BaseCrawler
from jd import jd_tools
from utils.consts import user_agent
from utils.db_manager import RedisManager


class JDCrawler(BaseCrawler):
    """京东爬虫实现类"""

    def __init__(self):
        super().__init__()
        self.redis_manager = RedisManager()
        self.base_search_url = "https://search.jd.com/Search?keyword={keyword}"
        self.base_detail_url = "https://item.jd.com/{sku}.html"
        self.login_url = "https://passport.jd.com/new/login.aspx"
        self.jd_home_page = 'https://www.jd.com/'
        # 添加实例变量保存对象引用
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def init_page(self) -> None:

        """初始化浏览器页面"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless_crawler)
        self.context = await self.browser.new_context(
            user_agent=user_agent,
        )
        # 获取随机Cookie
        # username, cookie_str = self.redis_manager.get_random_cookie()
        # # 如果有有效的cookie，设置到浏览器上下文
        # if username and cookie_str:
        #     # 解析Cookie字符串并设置Cookie
        #     cookies = []
        #     for cookie_item in cookie_str.split(';'):
        #         if not cookie_item.strip():
        #             continue
        #         parts = cookie_item.strip().split('=', 1)
        #         if len(parts) == 2:
        #             name, value = parts
        #             cookies.append({
        #                 'name': name.strip(),
        #                 'value': value.strip(),
        #                 'domain': '.jd.com',
        #                 'path': '/'
        #             })
        #
        #     await self.context.add_cookies(cookies)

        # 创建新页面
        self.page = await self.browser.new_page()
        await stealth_async(self.page)
        logger.info("浏览器页面初始化完成")

        await self.page.goto("https://bot.sannysoft.com/")
        await self.page.screenshot(path='test.png', full_page=True)
        await asyncio.sleep(999999)

    async def close(self) -> None:
        """关闭浏览器及相关资源"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器资源已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器资源时发生错误: {e}")

    async def search_products(self, keyword: str, page: int = 1) -> List[str]:
        # todo 添加分页支持，点击分页按钮
        """搜索商品，返回商品SKU列表"""
        try:
            if not self.page:
                logger.error("页面未初始化，请先调用init_page()")
                return []
            target_search_url = self.base_search_url.format(keyword=keyword)
            require_fields = jd_tools.required_cookie_fields
            logger.info("=====开始京东商品搜索=====")
            # 获取当前cookie
            cookies = await self.context.cookies()
            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}

            # 检查cookie是否包含所有必要字段
            missing_fields = [field for field in require_fields if field not in cookie_dict]

            if missing_fields:
                logger.info(f"Cookie缺少必要字段: {missing_fields}，先访问京东首页")
                # 先访问京东首页
                await self.page.goto("https://www.jd.com/")
                await self.page.wait_for_load_state("networkidle")
                # 检查是否有需要关闭的弹窗
                await self.close_popup()
                # 找到搜索输入框和搜索按钮
                await self.page.fill('input[id="key"][class="text"]', keyword)
                await self.page.click('button[class="button"]')
                # 检查是否有需要关闭的弹窗
                await self.close_popup()
                # 等待页面跳转到搜索结果页面
                await self.page.wait_for_url(f"**/Search**", timeout=30000)
                await self.page.wait_for_load_state("networkidle")

                # 检查是否有需要关闭的弹窗
                await self.close_popup()
                # 记录当前搜索页面URL
                current_url = self.page.url
                logger.info(f"已跳转到搜索结果页面: {current_url}")

                # 更新cookie到Redis
                updated_cookies = await self.context.cookies()
                updated_cookie_dict = {cookie['name']: cookie['value'] for cookie in updated_cookies}

                # 组合cookie字符串
                cookie_string = "; ".join([f"{name}={value}" for name, value in updated_cookie_dict.items()])

                # 获取用户名
                username = jd_tools.extract_username_pc(cookie_string)
                if username:
                    self.redis_manager.redis_client.hset(jd_tools.CookieMapRedisKey.pc, username, cookie_string)
                    logger.info(f"已更新用户 {username} 的Cookie")
            else:
                logger.info("Cookie已包含所有必要字段，直接访问搜索页面")
                await self.page.goto(target_search_url)
                await self.page.wait_for_load_state("networkidle")

            # 解析页面获取SKU列表
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            sku_elements = soup.select('li.gl-item')
            sku_list = [element.get('data-sku') for element in sku_elements if element.get('data-sku')]

            logger.info(f"搜索商品成功，找到 {len(sku_list)} 个商品")
            return sku_list
        except Exception as e:
            logger.error(f"搜索商品失败: {e}")
            return []

    async def get_product_detail(self, sku: str) -> Dict[str, Any]:
        """获取商品详情"""
        try:
            url = self.base_detail_url.format(sku=sku)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")

            # 解析页面获取商品信息
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # 获取商品标题
            title_element = soup.select_one('.sku-name')
            title = title_element.get_text().strip() if title_element else ""

            # 获取商品价格
            price_element = soup.select_one('.p-price .price')
            price = price_element.get_text().strip() if price_element else ""

            # 获取商品图片
            img_element = soup.select_one('.sku-name img')
            img_url = img_element.get('src') if img_element else ""

            return {
                "title": title,
                "price": price,
                "img": img_url
            }
        except Exception as e:
            logger.error(f"获取商品详情失败: {e}")
            return {}

    async def close_popup(self):
        try:
            close_button = await self.page.query_selector('img.umc-equity-close')
            if close_button:
                await close_button.click()
                await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"尝试关闭弹窗时出错: {e}")
