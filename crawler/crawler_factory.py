from typing import Dict, Type
from .base_crawler import BaseCrawler
from jd.jd_crawler_pc import JDCrawler as JDCrawlerPC


class CrawlerFactory:
    """爬虫工厂类，用于创建不同平台的爬虫实例"""

    _crawlers: Dict[str, Type[Dict[str, BaseCrawler]]] = {
        "jd": {
            "pc": JDCrawlerPC,
        },
    }

    @classmethod
    def create_crawler(cls, enterprise: str, platform: str) -> BaseCrawler:
        """
        创建指定平台的爬虫实例
        
        Args:
            enterprise: 电商平台，如 "jd" 表示京东
            platform: 平台类型 pc mobile
        Returns:
            BaseCrawler: 爬虫实例
            
        Raises:
            ValueError: 如果平台名称不支持
        """
        enterprise_lower = enterprise.lower()
        if enterprise_lower not in cls._crawlers:
            raise ValueError(f"不支持的电商平台: {enterprise}")
            
        platform_dict = cls._crawlers[enterprise_lower]
        platform_lower = platform.lower()
        if platform_lower not in platform_dict:
            raise ValueError(f"不支持的平台类型: {platform} (电商平台: {enterprise})")
            
        crawler_class = platform_dict[platform_lower]
        return crawler_class()
