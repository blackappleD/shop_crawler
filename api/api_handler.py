from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from crawler.crawler_factory import CrawlerFactory
from loguru import logger
from utils.cookie_updater import run_update
from pydantic import BaseModel

router = APIRouter()


class Response(BaseModel):
    """更新任务响应模型"""
    code: int
    message: str


@router.get("/product_search")
async def product_search(keyword: str = "手机", page: int = 1, platform: str = "jd") -> List[str]:
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
async def product_detail(sku: str = "100071214315", platform: str = "jd") -> Dict[str, Any]:
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


@router.post("/update_cookie")
async def update_cookie(background_tasks: BackgroundTasks) -> Response:
    """
    手动触发更新cookie任务
    此接口将在后台启动更新cookie的任务，不会阻塞请求
    Returns:
        Response: 任务状态响应
    """
    try:
        # 在后台任务中运行更新，不阻塞API响应
        background_tasks.add_task(run_update)
        return Response(
            code=1000,
            message="已成功启动更新cookie任务，请查看日志了解进度"
        )
    except Exception as e:
        logger.error(f"启动更新cookie任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
