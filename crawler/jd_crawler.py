from typing import List, Dict, Any
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from loguru import logger
from .base_crawler import BaseCrawler
from utils.db_manager import RedisManager

class JDCrawler(BaseCrawler):
    """京东爬虫实现类"""
    
    def __init__(self):
        super().__init__()
        self.redis_manager = RedisManager()
        self.search_url = "https://search.jd.com/Search?keyword={keyword}"
        self.detail_url = "https://item.jd.com/{sku}.html"
        self.login_url = "https://passport.jd.com/new/login.aspx"
        self.need_login_xml = '<a href="javascript:login();" class="link-login"><span>你好，</span><span class="style-red">请登录</span></a>'
        self.sku_xml = '<ul class="gl-warp clearfix" data-tpl="1"><li data-sku="100014366815" data-spu="100014366815" ware-type="10" bybt="0" class="gl-item"></li><li data-sku="100048306268" data-spu="100048306268" ware-type="10" bybt="0" class="gl-item"></ul>'
        self.title_xml = '<div class="sku-name"><img src="//img13.360buyimg.com/imagetools/jfs/t1/248227/2/26957/4011/6752d75cF80d258af/b01578d43f78670c.png" id="bgIcon" style="height:16px;display:none" alt="国家补贴"><img src="//img13.360buyimg.com/imagetools/jfs/t1/84452/25/26900/1090/66bc16cbF1e47fb52/30d3a11007fd979a.png" alt="新品">CHIYINNB【官网直营正品丨降噪Air4代】 华强北蓝牙耳机真无线适配苹果ANC降噪半入耳式iPhone16/15Pods 【原版正装全功能顶配版】 主动降噪+空间音頻</div>'
        self.price_xml = '<span class="p-price msbtPrice"><span>￥</span><span class="price J-p-10128414207655">128.00</span><span id="J_JdContent">补贴价</span></span>'
        self.img_xml = '<div class="sku-name"><img src="//img13.360buyimg.com/imagetools/jfs/t1/248227/2/26957/4011/6752d75cF80d258af/b01578d43f78670c.png" id="bgIcon" style="height:16px;display:none" alt="国家补贴"><img src="//img13.360buyimg.com/imagetools/jfs/t1/84452/25/26900/1090/66bc16cbF1e47fb52/30d3a11007fd979a.png" alt="新品">CHIYINNB【官网直营正品丨降噪Air4代】 华强北蓝牙耳机真无线适配苹果ANC降噪半入耳式iPhone16/15Pods 【原版正装全功能顶配版】 主动降噪+空间音頻</div>'
        
    async def init_page(self) -> None:
        """初始化浏览器页面"""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        self.page = await browser.new_page()
        
        # 设置随机Cookie
        cookies = self.redis_manager.get_all_cookies()
        if cookies:
            cookie_list = [{"name": k, "value": v, "domain": ".jd.com", "path": "/"} for k, v in cookies.items()]
            await self.page.context.add_cookies(cookie_list)
            
    async def check_login_status(self) -> bool:
        """检查登录状态"""
        try:
            login_element = await self.page.query_selector(self.need_login_xml)
            return login_element is None
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False
            
    async def search_products(self, keyword: str, page: int = 1) -> List[str]:
        """搜索商品，返回商品SKU列表"""
        try:
            url = self.search_url.format(keyword=keyword)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            
            # 检查登录状态
            if not await self.check_login_status():
                logger.warning("未登录状态，尝试使用新的Cookie")
                await self.init_page()
                return await self.search_products(keyword, page)
                
            # 解析页面获取SKU列表
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            sku_elements = soup.select('li.gl-item')
            sku_list = [element.get('data-sku') for element in sku_elements if element.get('data-sku')]
            
            return sku_list
        except Exception as e:
            logger.error(f"搜索商品失败: {e}")
            return []
            
    async def get_product_detail(self, sku: str) -> Dict[str, Any]:
        """获取商品详情"""
        try:
            url = self.detail_url.format(sku=sku)
            await self.page.goto(url)
            await self.page.wait_for_load_state("networkidle")
            
            # 检查登录状态
            if not await self.check_login_status():
                logger.warning("未登录状态，尝试使用新的Cookie")
                await self.init_page()
                return await self.get_product_detail(sku)
                
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