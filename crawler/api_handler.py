from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from .crawler_factory import CrawlerFactory
from loguru import logger

router = APIRouter()

@router.get("/product_search")
async def product_search(keyword: str, page: int = 1, platform: str = "jd") -> List[str]:
    """
    根据商品关键字查询商品sku列表
    
    Args:
        keyword: 搜索关键词
        page: 页码，默认为1
        platform: 平台名称，默认为"jd"
        
    Returns:
        List[str]: SKU列表
    """
    try:
        crawler = CrawlerFactory.create_crawler(platform)
        await crawler.init_page()
        try:
            sku_list = await crawler.search_products(keyword, page)
            return sku_list
        finally:
            await crawler.close()
    except Exception as e:
        logger.error(f"搜索商品失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/product_detail")
async def product_detail(sku: str, platform: str = "jd") -> Dict[str, Any]:
    """
    根据商品sku获取商品详细信息
    
    Args:
        sku: 商品SKU
        platform: 平台名称，默认为"jd"
        
    Returns:
        Dict[str, Any]: 商品详情，包含标题、价格和图片URL
    """
    try:
        crawler = CrawlerFactory.create_crawler(platform)
        await crawler.init_page()
        try:
            detail = await crawler.get_product_detail(sku)
            if not detail:
                raise HTTPException(status_code=404, detail="商品不存在")
            return detail
        finally:
            await crawler.close()
    except Exception as e:
        logger.error(f"获取商品详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 