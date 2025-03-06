import aiohttp
import argparse
import asyncio
from api.qinglong import QlApi, QlOpenApi
from api.send import SendApi
from utils.ck import get_invalid_ck_ids
from utils.db_manager import RedisManager, MysqlManager
from config import (
    qinglong_data,
    user_datas,
    cron_expression
)
import cv2
import json
from loguru import logger
import os
from playwright.async_api import Playwright, async_playwright
from playwright._impl._errors import TimeoutError
import random
import re
from PIL import Image  # 用于图像处理
import traceback
from typing import Union
from utils.consts import (
    jd_login_url,
    supported_types,
    supported_colors,
    supported_sms_func
)
from utils.tools import (
    get_tmp_dir,
    get_img_bytes,
    get_forbidden_users_dict,
    filter_forbidden_users,
    save_img,
    get_ocr,
    get_word,
    get_shape_location_by_type,
    get_shape_location_by_color,
    rgba2rgb,
    send_msg,
    new_solve_slider_captcha,
    ddddocr_find_files_pic,
    expand_coordinates,
    cv2_save_img,
    ddddocr_find_bytes_pic,
    solve_slider_captcha,
    validate_proxy_config,
    is_valid_verification_code,
    filter_cks,
    extract_pt_pin,
    desensitize_account
)
import uvicorn
from datetime import datetime, timedelta
from croniter import croniter
from crawler import router as crawler_router

"""
基于playwright做的
"""
logger.add(
    sink="main.log",
    level="DEBUG"
)

try:
    # 账号是否脱敏的开关
    from config import enable_desensitize
except ImportError:
    enable_desensitize = False

# 导入新增配置
try:
    from config import (
        mysql_config,
        redis_config,
        account_source,
        cookie_source,
        cookie_target,
        sms_func
    )
except ImportError:
    # 默认使用原有方式
    mysql_config = {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "", "database": ""}
    redis_config = {"host": "127.0.0.1", "port": 6379, "db": 0, "password": None}
    account_source = "config"
    cookie_source = "qinglong"
    cookie_target = "qinglong"
    sms_func = "manual_input"  # 默认使用手动输入


async def download_image(url, filepath):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                with open(filepath, 'wb') as f:
                    f.write(await response.read())
                print(f"Image downloaded to {filepath}")
            else:
                print(f"Failed to download image. Status code: {response.status}")


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


async def auto_move_slide_v2(page, retry_times: int = 2, slider_selector: str = 'img.move-img',
                             move_solve_type: str = ""):
    for i in range(retry_times):
        logger.info(f'第{i + 1}次开启滑块验证')
        # 查找小图
        try:
            # 查找小图
            await page.wait_for_selector('.captcha_drop', state='visible', timeout=3000)
        except Exception as e:
            logger.info('未找到验证码框, 退出滑块验证')
            return
        await auto_move_slide(page, retry_times=5, slider_selector=slider_selector, move_solve_type=move_solve_type)

        # 判断是否一次过了滑块
        captcha_drop_visible = await page.is_visible('.captcha_drop')

        # 存在就重新滑一次
        if captcha_drop_visible:
            if i == retry_times - 1:
                return
            logger.info('一次过滑块失败, 再次尝试滑块验证')
            await page.wait_for_selector('.captcha_drop', state='visible', timeout=3000)
            # 点外键
            sign_locator = page.locator('#header').locator('.text-header')
            sign_locator_box = await sign_locator.bounding_box()
            sign_locator_left_x = sign_locator_box['x']
            sign_locator_left_y = sign_locator_box['y']
            await page.mouse.click(sign_locator_left_x, sign_locator_left_y)
            await asyncio.sleep(1)
            # 提交键
            submit_locator = page.locator('.btn.J_ping.active')
            await submit_locator.click()
            await asyncio.sleep(1)
            continue
        return


async def auto_move_slide(page, retry_times: int = 2, slider_selector: str = 'img.move-img', move_solve_type: str = ""):
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
            if target_color in supported_colors:
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
            if shape_type in supported_types:
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


async def sms_recognition(page, user, user_data_dict, mode):
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


async def get_jd_pt_key(playwright: Playwright, user, user_data_dict, mode) -> Union[str, None]:
    """
    获取jd的pt_key
    
    :param playwright: Playwright实例
    :param user: 用户名
    :param user_data_dict: 用户数据字典
    :param mode: 运行模式
    :return: pt_key或None
    """

    try:
        from config import headless
    except ImportError:
        headless = False

    args = '--no-sandbox', '--disable-setuid-sandbox', '--disable-software-rasterizer', '--disable-gpu'

    try:
        # 引入代理
        from config import proxy
        # 检查代理的配置
        is_proxy_valid, msg = validate_proxy_config(proxy)
        if not is_proxy_valid:
            logger.error(msg)
            proxy = None
        if msg == "未配置代理":
            logger.info(msg)
            proxy = None
    except ImportError:
        logger.info("未配置代理")
        proxy = None

    browser = await playwright.chromium.launch(headless=headless, args=args, proxy=proxy)
    try:
        # 引入UA
        from config import user_agent
    except ImportError:
        from utils.consts import user_agent
    context = await browser.new_context(user_agent=user_agent)

    try:
        page = await context.new_page()
        await page.set_viewport_size({"width": 360, "height": 640})
        await page.goto(jd_login_url)

        if user_data_dict[user].get("user_type") == "qq":
            await page.get_by_role("checkbox").check()
            await asyncio.sleep(1)
            # 点击QQ登录
            await page.locator("a.quick-qq").click()
            await asyncio.sleep(1)

            # 等待 iframe 加载完成
            await page.wait_for_selector("#ptlogin_iframe")
            # 切换到 iframe
            iframe = page.frame(name="ptlogin_iframe")

            # 通过 id 选择 "密码登录" 链接并点击
            await iframe.locator("#switcher_plogin").click()
            await asyncio.sleep(1)
            # 填写账号
            username_input = iframe.locator("#u")  # 替换为实际的账号
            for u in user:
                await username_input.type(u, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)
            await asyncio.sleep(1)
            # 填写密码
            password_input = iframe.locator("#p")  # 替换为实际的密码
            password = user_data_dict[user]["password"]
            for p in password:
                await password_input.type(p, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)
            await asyncio.sleep(1)
            # 点击登录按钮
            await iframe.locator("#login_button").click()
            await asyncio.sleep(1)
            # 这里检测安全验证
            new_vcode_area = iframe.locator("div#newVcodeArea")
            style = await new_vcode_area.get_attribute("style")
            if style and "display: block" in style:
                if await new_vcode_area.get_by_text("安全验证").text_content() == "安全验证":
                    logger.error(f"QQ号{user}需要安全验证, 登录失败，请使用其它账号类型")
                    raise Exception(f"QQ号{user}需要安全验证, 登录失败，请使用其它账号类型")

        else:
            await page.get_by_text("账号密码登录").click()

            username_input = page.locator("#username")
            for u in user:
                await username_input.type(u, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)

            password_input = page.locator("#pwd")
            password = user_data_dict[user]["password"]
            for p in password:
                await password_input.type(p, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)

            await asyncio.sleep(random.random())
            await page.locator('.policy_tip-checkbox').click()
            await asyncio.sleep(random.random())
            await page.locator('.btn.J_ping.active').click()

            # 自动识别移动滑块验证码
            await asyncio.sleep(1)
            await auto_move_slide_v2(page, retry_times=5)

            # 自动验证形状验证码
            await asyncio.sleep(1)
            await auto_shape(page, retry_times=30)

            # 进行短信验证识别
            await asyncio.sleep(1)
            if await page.locator('text="手机短信验证"').count() != 0:
                logger.info("开始短信验证码识别环节")
                await sms_recognition(page, user, user_data_dict, mode)

            # 进行手机语音验证识别
            if await page.locator('div#header .text-header:has-text("手机语音验证")').count() > 0:
                logger.info("检测到手机语音验证页面,开始识别")
                await voice_verification(page, user, user_data_dict, mode)

            # 检查警告,如账号存在风险或账密不正确等
            await check_notice(page)

        # 等待验证码通过
        logger.info("等待获取cookie...")
        await page.wait_for_selector('#msShortcutMenu', state='visible', timeout=120000)

        cookies = await context.cookies()
        for cookie in cookies:
            if cookie['name'] == 'pt_key':
                pt_key = cookie["value"]
                return pt_key

        return None

    except Exception as e:
        traceback.print_exc()
        return None

    finally:
        await context.close()
        await browser.close()


async def get_ql_api(ql_data):
    """
    封装了QL的登录
    """
    logger.info("开始获取QL登录态......")

    # 优化client_id和client_secret
    client_id = ql_data.get('client_id')
    client_secret = ql_data.get('client_secret')
    if client_id and client_secret:
        logger.info("使用client_id和client_secret登录......")
        qlapi = QlOpenApi(ql_data["url"])
        response = await qlapi.login(client_id=client_id, client_secret=client_secret)
        if response['code'] == 200:
            logger.info("client_id和client_secret正常可用......")
            return qlapi
        else:
            logger.info("client_id和client_secret异常......")

    qlapi = QlApi(ql_data["url"])

    # 其次用token
    token = ql_data.get('token')
    if token:
        logger.info("已设置TOKEN,开始检测TOKEN状态......")
        qlapi.login_by_token(token)

        # 如果token失效，就用账号密码登录
        response = await qlapi.get_envs()
        if response['code'] == 401:
            logger.info("Token已失效, 正使用账号密码获取QL登录态......")
            response = await qlapi.login_by_username(ql_data.get("username"), ql_data.get("password"))
            if response['code'] != 200:
                logger.error(f"账号密码登录失败. response: {response}")
                raise Exception(f"账号密码登录失败. response: {response}")
        else:
            logger.info("Token正常可用......")
    else:
        # 最后用账号密码
        logger.info("正使用账号密码获取QL登录态......")
        response = await qlapi.login_by_username(ql_data.get("username"), ql_data.get("password"))
        if response['code'] != 200:
            logger.error(f"账号密码登录失败. response: {response}")
            raise Exception(f"账号密码登录失败.response: {response}")
    return qlapi


async def init_data_sources():
    """初始化数据源连接"""
    redis_manager = None
    mysql_manager = None
    qlapi = None

    # 初始化Redis连接（如果需要）
    if cookie_source == "redis" or cookie_target == "redis":
        redis_manager = RedisManager(
            host=redis_config.get("host", "127.0.0.1"),
            port=redis_config.get("port", 6379),
            db=redis_config.get("db", 0),
            password=redis_config.get("password")
        )

    # 初始化MySQL连接（如果需要）
    if account_source == "mysql":
        mysql_manager = MysqlManager(
            host=mysql_config.get("host", "127.0.0.1"),
            port=mysql_config.get("port", 3306),
            user=mysql_config.get("user", "root"),
            password=mysql_config.get("password", ""),
            database=mysql_config.get("database", "")
        )

    # 初始化青龙API（如果需要）
    if cookie_source == "qinglong" or cookie_target == "qinglong":
        qlapi = await get_ql_api(qinglong_data)

    return redis_manager, mysql_manager, qlapi


async def get_user_data(mysql_manager):
    """获取用户数据"""
    if account_source == "config":
        # 使用配置文件中的用户数据
        return user_datas
    elif account_source == "mysql" and mysql_manager:
        # 从MySQL获取用户数据
        user_data_dict = {}
        accounts = mysql_manager.get_all_accounts()
        for account in accounts:
            username = account.get("username")
            user_data_dict[username] = {
                "password": account.get("password"),
                "pt_pin": username,  # 使用username作为pt_pin
                "phone": account.get("phone"),
                "sms_func": sms_func,  # 使用全局配置的短信验证方式
            }
        return user_data_dict
    return {}


async def get_cookies_data(redis_manager, qlapi):
    """获取Cookie数据"""
    jd_ck_env_datas = []
    update_all_accounts = False
    
    if cookie_source == "qinglong" and qlapi:
        # 从青龙面板获取Cookie
        response = await qlapi.get_envs()
        if response['code'] == 200:
            logger.info("获取青龙环境变量成功")
            env_data = response['data']
            # 获取值为JD_COOKIE的环境变量
            jd_ck_env_datas = filter_cks(env_data, name='JD_COOKIE')
            # 从value中过滤出pt_pin, 注意只支持单行单pt_pin
            jd_ck_env_datas = [{**x, 'pt_pin': extract_pt_pin(x['value'])} for x in jd_ck_env_datas if extract_pt_pin(x['value'])]
        else:
            logger.error(f"获取青龙环境变量失败， response: {response}")
            raise Exception(f"获取青龙环境变量失败， response: {response}")
    elif cookie_source == "redis" and redis_manager:
        # 从Redis获取Cookie
        logger.info("从Redis获取Cookie")
        cookies_dict = redis_manager.get_all_cookies()
        logger.info(f"从Redis获取到的Cookie数据类型: {type(cookies_dict)}, 值: {cookies_dict}")
        
        # 检查Redis中是否有Cookie数据
        if cookies_dict is None or (isinstance(cookies_dict, dict) and len(cookies_dict) == 0):
            logger.info("Redis中的JD_COOKIE_MAP为空或不存在，将更新所有账号的Cookie")
            update_all_accounts = True
        else:
            logger.info(f"Redis中的JD_COOKIE_MAP包含 {len(cookies_dict)} 个账号的Cookie")
        
        for username, cookie in cookies_dict.items() if cookies_dict else {}:
            pt_pin = extract_pt_pin(cookie)
            if pt_pin:
                jd_ck_env_datas.append({
                    'id': username,  # 使用username作为ID
                    'value': cookie,
                    'status': 0,  # 默认启用状态
                    'pt_pin': pt_pin,
                    'name': 'JD_COOKIE',
                    'remarks': f'用户: {username}'
                })
    
    return jd_ck_env_datas, update_all_accounts


async def check_cookies(jd_ck_env_datas, qlapi):
    """检查Cookie有效性"""
    try:
        logger.info("检测CK任务开始")
        # 先获取启用中的env_data
        up_jd_ck_list = filter_cks(jd_ck_env_datas, status=0, name='JD_COOKIE')
        # 这一步会去检测这些JD_COOKIE
        invalid_cks_id_list = await get_invalid_ck_ids(up_jd_ck_list)
        if invalid_cks_id_list:
            # 更新jd_ck_env_datas中失效CK的状态
            jd_ck_env_datas = [
                {**x, 'status': 1} if x.get('id') in invalid_cks_id_list or x.get('_id') in invalid_cks_id_list else x
                for x in jd_ck_env_datas]

            # 如果使用青龙面板，则禁用失效环境变量
            if cookie_source == "qinglong" and qlapi:
                ck_ids_datas = bytes(json.dumps(invalid_cks_id_list), 'utf-8')
                await qlapi.envs_disable(data=ck_ids_datas)
        logger.info("检测CK任务完成")
        return jd_ck_env_datas
    except Exception as e:
        traceback.print_exc()
        logger.error(f"检测CK任务失败, 跳过检测, 报错原因为{e}")
        return jd_ck_env_datas


async def get_update_users(jd_ck_env_datas, user_data_dict, update_all_accounts):
    """获取需要更新的用户"""
    if update_all_accounts:
        logger.info("即将更新所有账号的Cookie")
        user_dict = {}
        for username, user_data in user_data_dict.items():
            user_dict[username] = {
                'id': username,
                'value': '',  # 空值，稍后会在更新时填充
                'name': 'JD_COOKIE',
                'remarks': f'用户: {username}'
            }
        return user_dict

    # 获取需强制更新pt_pin
    force_update_pt_pins = [user_data_dict[key]["pt_pin"] for key in user_data_dict if
                            user_data_dict[key].get("force_update") is True]
    # 获取禁用和需要强制更新的users
    forbidden_users = [x for x in jd_ck_env_datas if (x['status'] == 1 or x['pt_pin'] in force_update_pt_pins)]

    if not forbidden_users:
        logger.info("所有COOKIE环境变量正常，无需更新")
        return {}

    # 获取需要的字段
    filter_users_list = filter_forbidden_users(forbidden_users, ['_id', 'id', 'value', 'remarks', 'name'])

    # 生成字典
    user_dict = get_forbidden_users_dict(filter_users_list, user_data_dict)
    if not user_dict:
        logger.info("失效的CK信息未配置在user_datas内，无需更新")

    return user_dict


async def update_cookie(user, user_dict, user_data_dict, redis_manager, qlapi, send_api, mode):
    """更新单个用户的Cookie"""
    logger.info(f"开始更新{desensitize_account(user, enable_desensitize)}")

    # 登录JD获取pt_key
    async with async_playwright() as playwright:
        pt_key = await get_jd_pt_key(playwright, user, user_data_dict, mode)

    if pt_key is None:
        logger.error(f"获取pt_key失败")
        await send_msg(send_api, send_type=1, msg=f"{desensitize_account(user, enable_desensitize)} 更新失败")
        return False

    req_data = user_dict[user]
    new_cookie = f"pt_key={pt_key};pt_pin={user_data_dict[user]['pt_pin']};"
    req_data["value"] = new_cookie
    logger.info(f"更新内容为{req_data}")

    # 根据配置决定存储位置
    if cookie_target == "qinglong" and qlapi:
        # 更新青龙面板的Cookie
        data = json.dumps(req_data)
        response = await qlapi.set_envs(data=data)
        if response['code'] != 200:
            logger.error(f"{desensitize_account(user, enable_desensitize)}更新失败, response: {response}")
            await send_msg(send_api, send_type=1, msg=f"{desensitize_account(user, enable_desensitize)} 更新失败")
            return False

        # 启用环境变量
        req_id = f"[{req_data['id']}]" if 'id' in req_data.keys() else f'[\"{req_data["_id"]}\"]'
        data = bytes(req_id, 'utf-8')
        response = await qlapi.envs_enable(data=data)
        if response['code'] != 200:
            logger.error(f"{desensitize_account(user, enable_desensitize)}启用失败, response: {response}")
            return False

    elif cookie_target == "redis" and redis_manager:
        # 更新Redis中的Cookie
        if not redis_manager.set_cookie(user, new_cookie):
            logger.error(f"{desensitize_account(user, enable_desensitize)}更新失败")
            await send_msg(send_api, send_type=1, msg=f"{desensitize_account(user, enable_desensitize)} 更新失败")
            return False

    logger.info(f"{desensitize_account(user, enable_desensitize)}更新成功")
    await send_msg(send_api, send_type=0, msg=f"{desensitize_account(user, enable_desensitize)} 更新成功")
    return True


async def main(mode: str = None):
    """
    :param mode 运行模式, 当mode = cron时，sms_func为 manual_input时，将自动传成no
    """
    try:
        send_api = SendApi("ql")

        # 1. 初始化数据源
        redis_manager, mysql_manager, qlapi = await init_data_sources()

        # 2. 获取用户数据
        user_data_dict = await get_user_data(mysql_manager)

        # 3. 获取Cookie数据
        jd_ck_env_datas, update_all_accounts = await get_cookies_data(redis_manager, qlapi)

        # 4. 检查Cookie有效性（如果不是更新所有账号）
        if not update_all_accounts:
            jd_ck_env_datas = await check_cookies(jd_ck_env_datas, qlapi)

        # 5. 获取需要更新的用户
        user_dict = await get_update_users(jd_ck_env_datas, user_data_dict, update_all_accounts)
        if not user_dict:
            # 关闭MySQL连接
            if mysql_manager:
                mysql_manager.close()
            return

        # 6. 更新Cookie
        for user in user_dict:
            await update_cookie(user, user_dict, user_data_dict, redis_manager, qlapi, send_api, mode)

        # 7. 关闭MySQL连接
        if mysql_manager:
            mysql_manager.close()

    except Exception as e:
        traceback.print_exc()

def parse_args():
    """解析参数"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mode', choices=['cron'], help="运行的main的模式(例如: 'cron')")
    parser.add_argument('-p', '--port', type=int, default=8000, help="服务运行的端口号")
    parser.add_argument('--host', default="0.0.0.0", help="服务运行的主机地址")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    # 启动FastAPI服务
    uvicorn.run(
        "app:app",  # 使用模块导入方式
        host=args.host,
        port=args.port,
        log_level="info"
    )
