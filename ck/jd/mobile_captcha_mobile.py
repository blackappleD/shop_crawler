import aiohttp
import argparse
import asyncio
import cv2
from loguru import logger
import os
from playwright.async_api import Playwright
from playwright._impl._errors import TimeoutError
import random
import re
from PIL import Image  # 用于图像处理
import traceback
from typing import Union
import utils.consts as Consts
from utils.cookie_updater import (
    run_update
)

from utils.tools import (
    get_tmp_dir,
    get_img_bytes,
    save_img,
    get_ocr,
    get_word,
    get_shape_location_by_type,
    get_shape_location_by_color,
    rgba2rgb,
    new_solve_slider_captcha,
    ddddocr_find_files_pic,
    expand_coordinates,
    cv2_save_img,
    ddddocr_find_bytes_pic,
    solve_slider_captcha,
    validate_proxy_config,
    is_valid_verification_code,
)
import uvicorn


async def auto_move_slide_mobile(page, slider_selector, retry_times: int = 2, move_solve_type: str = ""):
    """
    自动识别移动滑块验证码
    """

    for i in range(retry_times):
        logger.info(f'第{i + 1}次尝试自动移动滑块中...')
        try:
            # 查找小图
            await page.wait_for_selector('#small_img', state='visible', timeout=3000)
        except Exception as e:
            # 未找到元素，认为成功，退出循环
            logger.info('未找到小图,退出移动滑块')
            break

        # 获取 src 属性
        small_src = await page.locator('#small_img').get_attribute('src')
        background_src = await page.locator('#cpc_img').get_attribute('src')

        # 获取 bytes
        small_img_bytes = get_img_bytes(small_src)
        background_img_bytes = get_img_bytes(background_src)

        # 保存小图
        small_img_path = save_img('small_img', small_img_bytes)
        small_img_width = await page.evaluate(
            '() => { return document.getElementById("small_img").clientWidth; }')  # 获取网页的图片尺寸
        small_img_height = await page.evaluate(
            '() => { return document.getElementById("small_img").clientHeight; }')  # 获取网页的图片尺寸
        small_image = Image.open(small_img_path)  # 打开图像
        resized_small_image = small_image.resize((small_img_width, small_img_height))  # 调整图像尺寸
        resized_small_image.save(small_img_path)  # 保存调整后的图像

        # 保存大图
        background_img_path = save_img('background_img', background_img_bytes)
        background_img_width = await page.evaluate(
            '() => { return document.getElementById("cpc_img").clientWidth; }')  # 获取网页的图片尺寸
        background_img_height = await page.evaluate(
            '() => { return document.getElementById("cpc_img").clientHeight; }')  # 获取网页的图片尺寸
        background_image = Image.open(background_img_path)  # 打开图像
        resized_background_image = background_image.resize((background_img_width, background_img_height))  # 调整图像尺寸
        resized_background_image.save(background_img_path)  # 保存调整后的图像

        # 获取滑块
        slider = page.locator(slider_selector)
        await asyncio.sleep(1)

        # 这里是一个标准算法偏差
        slide_difference = 10

        if move_solve_type == "old":
            # 用于调试
            distance = ddddocr_find_bytes_pic(small_img_bytes, background_img_bytes)
            await asyncio.sleep(1)
            await solve_slider_captcha(page, slider, distance, slide_difference)
            await asyncio.sleep(1)
            continue
        # 获取要移动的长度
        distance = ddddocr_find_files_pic(small_img_path, background_img_path)
        await asyncio.sleep(1)
        # 移动滑块
        await new_solve_slider_captcha(page, slider, distance, slide_difference)
        await asyncio.sleep(1)


async def sms_recognition_mobile(page, user, user_data_dict, mode):
    """
    短信验证码识别
    """
    try:
        from config import sms_func, sms_webhook
    except ImportError:
        sms_func = "no"
        sms_webhook = ""

    # 优先使用用户自己的配置
    sms_func = user_data_dict[user].get("sms_func", sms_func)

    # 如果是cron模式，且sms_func为manual_input，则自动转为no
    if mode == "cron" and sms_func == "manual_input":
        sms_func = "no"

    if sms_func == "no":
        logger.info("短信验证码识别已关闭")
        return False

    # 等待短信验证码输入框出现
    try:
        await page.wait_for_selector("#authcode", timeout=1000)
    except TimeoutError:
        logger.info("没有触发短信验证码")
        return False

    logger.info("触发短信验证码")
    if sms_func == "manual_input":
        try:
            from inputimeout import inputimeout, TimeoutOccurred
            verification_code = inputimeout(prompt='请输入短信验证码: ', timeout=60)
            if not is_valid_verification_code(verification_code):
                logger.error("验证码格式错误")
                return False
        except TimeoutOccurred:
            logger.error("验证码输入超时")
            return False
    elif sms_func == "webhook":
        # 优先使用用户自己的配置
        sms_webhook = user_data_dict[user].get("sms_webhook", sms_webhook)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sms_webhook) as response:
                    if response.status == 200:
                        verification_code = await response.text()
                        if not is_valid_verification_code(verification_code):
                            logger.error("验证码格式错误")
                            return False
                    else:
                        logger.error(f"获取验证码失败，状态码：{response.status}")
                        return False
        except Exception as e:
            logger.error(f"获取验证码失败，错误信息：{e}")
            return False
    else:
        logger.error(f"不支持的短信验证码识别方式：{sms_func}")
        return False

    # 输入验证码
    await page.fill("#authcode", verification_code)
    # 点击登录
    await page.click(".btn-sms-login")
    return True


async def voice_verification(page, user, user_data_dict, mode):
    """
    语音验证码识别
    """
    try:
        from config import voice_func
    except ImportError:
        voice_func = "no"

    # 优先使用用户自己的配置
    voice_func = user_data_dict[user].get("voice_func", voice_func)

    # 如果是cron模式，且voice_func为manual_input，则自动转为no
    if mode == "cron" and voice_func == "manual_input":
        voice_func = "no"

    if voice_func == "no":
        logger.info("语音验证码识别已关闭")
        return False

    # 等待语音验证码输入框出现
    try:
        await page.wait_for_selector("#authcode", timeout=1000)
    except TimeoutError:
        logger.info("没有触发语音验证码")
        return False

    logger.info("触发语音验证码")
    if voice_func == "manual_input":
        try:
            from inputimeout import inputimeout, TimeoutOccurred
            verification_code = inputimeout(prompt='请输入语音验证码: ', timeout=60)
            if not is_valid_verification_code(verification_code):
                logger.error("验证码格式错误")
                return False
        except TimeoutOccurred:
            logger.error("验证码输入超时")
            return False
    else:
        logger.error(f"不支持的语音验证码识别方式：{voice_func}")
        return False

    # 输入验证码
    await page.fill("#authcode", verification_code)
    # 点击登录
    await page.click(".btn-sms-login")
    return True


async def auto_shape(page, retry_times: int = 5):
    # 图像识别
    ocr = get_ocr(beta=True)
    # 文字识别
    det = get_ocr(det=True)
    # 自己训练的ocr, 提高文字识别度
    my_ocr = get_ocr(det=False, ocr=False, import_onnx_path="myocr_v1.onnx", charsets_path="charsets.json")
    """
    自动识别滑块验证码
    """
    for i in range(retry_times):
        logger.info(f'第{i + 1}次自动识别形状中...')
        try:
            # 查找小图
            await page.wait_for_selector('div.captcha_footer img', state='visible', timeout=3000)
        except Exception as e:
            # 未找到元素，认为成功，退出循环
            logger.info('未找到形状图,退出识别状态')
            break

        tmp_dir = get_tmp_dir()

        background_img_path = os.path.join(tmp_dir, f'background_img.png')
        # 获取大图元素
        background_locator = page.locator('#cpc_img')
        # 获取元素的位置和尺寸
        backend_bounding_box = await background_locator.bounding_box()
        backend_top_left_x = backend_bounding_box['x']
        backend_top_left_y = backend_bounding_box['y']

        # 截取元素区域
        await page.screenshot(path=background_img_path, clip=backend_bounding_box)

        # 获取 图片的src 属性和button按键
        word_img_src = await page.locator('div.captcha_footer img').get_attribute('src')
        button = page.locator('div.captcha_footer button#submit-btn')

        # 找到刷新按钮
        refresh_button = page.locator('.jcap_refresh')

        # 获取文字图并保存
        word_img_bytes = get_img_bytes(word_img_src)
        rgba_word_img_path = save_img('rgba_word_img', word_img_bytes)

        # 文字图是RGBA的，有蒙板识别不了，需要转成RGB
        rgb_word_img_path = rgba2rgb('rgb_word_img', rgba_word_img_path)

        # 获取问题的文字
        word = get_word(ocr, rgb_word_img_path)

        if word.find('色') > 0:
            target_color = word.split('请选出图中')[1].split('的图形')[0]
            if target_color in Consts.supported_colors:
                logger.info(f'正在点击中......')
                # 获取点的中心点
                center_x, center_y = get_shape_location_by_color(background_img_path, target_color)
                if center_x is None and center_y is None:
                    logger.info(f'识别失败,刷新中......')
                    await refresh_button.click()
                    await asyncio.sleep(random.uniform(2, 4))
                    continue
                # 得到网页上的中心点
                x, y = backend_top_left_x + center_x, backend_top_left_y + center_y
                # 点击图片
                await page.mouse.click(x, y)
                await asyncio.sleep(random.uniform(1, 4))
                # 点击确定
                await button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue
            else:
                logger.info(f'不支持{target_color},刷新中......')
                # 刷新
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue

        # 这里是文字验证码了
        elif word.find('依次') > 0:
            logger.info(f'开始文字识别,点击中......')
            # 获取文字的顺序列表
            try:
                target_char_list = list(re.findall(r'[\u4e00-\u9fff]+', word)[1])
            except IndexError:
                logger.info(f'识别文字出错,刷新中......')
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue

            target_char_len = len(target_char_list)

            # 识别字数不对
            if target_char_len < 4:
                logger.info(f'识别的字数小于4,刷新中......')
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue

            # 取前4个的文字
            target_char_list = target_char_list[:4]

            # 定义【文字, 坐标】的列表
            target_list = [[x, []] for x in target_char_list]

            # 获取大图的二进制
            background_locator = page.locator('#cpc_img')
            background_locator_src = await background_locator.get_attribute('src')
            background_locator_bytes = get_img_bytes(background_locator_src)
            bboxes = det.detection(background_locator_bytes)

            count = 0
            im = cv2.imread(background_img_path)
            for bbox in bboxes:
                # 左上角
                x1, y1, x2, y2 = bbox
                # 做了一下扩大
                expanded_x1, expanded_y1, expanded_x2, expanded_y2 = expand_coordinates(x1, y1, x2, y2, 10)
                im2 = im[expanded_y1:expanded_y2, expanded_x1:expanded_x2]
                img_path = cv2_save_img('word', im2)
                image_bytes = open(img_path, "rb").read()
                result = my_ocr.classification(image_bytes)
                if result in target_char_list:
                    for index, target in enumerate(target_list):
                        if result == target[0] and target[0] is not None:
                            x = x1 + (x2 - x1) / 2
                            y = y1 + (y2 - y1) / 2
                            target_list[index][1] = [x, y]
                            count += 1

            if count != target_char_len:
                logger.info(f'文字识别失败,刷新中......')
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue

            await asyncio.sleep(random.uniform(0, 1))
            try:
                for char in target_list:
                    center_x = char[1][0]
                    center_y = char[1][1]
                    # 得到网页上的中心点
                    x, y = backend_top_left_x + center_x, backend_top_left_y + center_y
                    # 点击图片
                    await page.mouse.click(x, y)
                    await asyncio.sleep(random.uniform(1, 4))
            except IndexError:
                logger.info(f'识别文字出错,刷新中......')
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue
            # 点击确定
            await button.click()
            await asyncio.sleep(random.uniform(2, 4))

        else:
            shape_type = word.split('请选出图中的')[1]
            if shape_type in Consts.supported_types:
                logger.info(f'已找到图形,点击中......')
                if shape_type == "圆环":
                    shape_type = shape_type.replace('圆环', '圆形')
                # 获取点的中心点
                center_x, center_y = get_shape_location_by_type(background_img_path, shape_type)
                if center_x is None and center_y is None:
                    logger.info(f'识别失败,刷新中......')
                    await refresh_button.click()
                    await asyncio.sleep(random.uniform(2, 4))
                    continue
                # 得到网页上的中心点
                x, y = backend_top_left_x + center_x, backend_top_left_y + center_y
                # 点击图片
                await page.mouse.click(x, y)
                await asyncio.sleep(random.uniform(1, 4))
                # 点击确定
                await button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue
            else:
                logger.info(f'不支持{shape_type},刷新中......')
                # 刷新
                await refresh_button.click()
                await asyncio.sleep(random.uniform(2, 4))
                continue


async def check_notice(page):
    try:
        logger.info("检查登录是否报错")
        notice = await page.wait_for_function(
            """
            () => {
                const notice = document.querySelectorAll('.notice')[1];
                return notice && notice.textContent.trim() !== '' ? notice.textContent.trim() : false;
            }
            """,
            timeout=3000
        )
        raise RuntimeError(notice)
    except TimeoutError:
        logger.info("登录未发现报错")
        return
