from typing import Dict, Type
from .base_crawler import BaseCrawler
from .jd_crawler import JDCrawler

class CrawlerFactory:
    """爬虫工厂类，用于创建不同平台的爬虫实例"""
    
    _crawlers: Dict[str, Type[BaseCrawler]] = {
        "jd": JDCrawler,
        # 后续可以添加其他平台的爬虫
    }
    
    @classmethod
    def create_crawler(cls, platform: str) -> BaseCrawler:
        """
        创建指定平台的爬虫实例
        
        Args:
            platform: 平台名称，如 "jd" 表示京东
            
        Returns:
            BaseCrawler: 爬虫实例
            
        Raises:
            ValueError: 如果平台名称不支持
        """
        crawler_class = cls._crawlers.get(platform.lower())
        if not crawler_class:
            raise ValueError(f"不支持的平台: {platform}")
        return crawler_class() 