from abc import ABC, abstractmethod
from typing import List, Dict, Any
from playwright.async_api import Page

class BaseCrawler(ABC):
    """基础爬虫类，定义通用的爬虫接口和功能"""
    
    def __init__(self):
        self.page: Page = None
        
    @abstractmethod
    async def init_page(self) -> None:
        """初始化浏览器页面"""
        pass
        
    @abstractmethod
    async def check_login_status(self) -> bool:
        """检查登录状态"""
        pass
        
    @abstractmethod
    async def search_products(self, keyword: str, page: int = 1) -> List[str]:
        """搜索商品，返回商品SKU列表"""
        pass
        
    @abstractmethod
    async def get_product_detail(self, sku: str) -> Dict[str, Any]:
        """获取商品详情"""
        pass
        
    async def close(self) -> None:
        """关闭浏览器页面"""
        if self.page:
            await self.page.close() 