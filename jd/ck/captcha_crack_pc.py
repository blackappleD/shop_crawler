import aiohttp
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

from jd import jd_tools
from utils.consts import Account, jd_login_url, PcLoginSelectors, MobileLoginSelectors, supported_colors, \
    supported_types, AccountStatus, SmsFunc, RunMode, Enterprise
from utils.db_manager import MysqlManager, RedisManager
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
    get_md5,
)


async def get_jd_cookie_pc(playwright: Playwright, account: Account, mysql_manager: MysqlManager, mode) -> Union[
    str, None]:
    """
    获取jd的cookie
    :param playwright: Playwright实例
    :param mode: 运行模式
    :param account: 账号信息
    :param mysql_manager: MySQL管理器，用于更新账号状态
    :return: 完整cookie字符串或None
    """

    global headless_login
    try:
        from config import headless_login
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

    browser = await playwright.chromium.launch(headless=headless_login, args=args, proxy=proxy)
    try:
        # 引入UA
        from config import user_agent
    except ImportError:
        from utils.consts import user_agent
    context = await browser.new_context(user_agent=user_agent)

    try:
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.goto(jd_login_url)

        if account.user_type == "qq":
            # 点击QQ登录
            await page.locator("b.QQ-icon").click()
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
            for u in account.username:
                await username_input.type(u, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)
            await asyncio.sleep(1)
            # 填写密码
            password_input = iframe.locator("#p")  # 替换为实际的密码
            for p in account.password:
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
                    logger.error(f"QQ号{account.username}需要安全验证, 登录失败，请使用其它账号类型")
                    raise Exception(f"QQ号{account.username}需要安全验证, 登录失败，请使用其它账号类型")

        else:
            await page.get_by_text("密码登录").click()

            username_input = page.locator("#loginname")
            for u in account.username:
                await username_input.type(u, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)

            password_input = page.locator("#nloginpwd")
            for p in account.password:
                await password_input.type(p, no_wait_after=True)
                await asyncio.sleep(random.random() / 10)

            await page.locator("#loginsubmit").click()

            # 自动识别移动滑块验证码
            await asyncio.sleep(1)
            await auto_move_slide_v2(page, retry_times=5)

            # 自动验证形状验证码
            # await asyncio.sleep(1)
            # await auto_shape(page, retry_times=30)

            # 进行短信验证识别
            await asyncio.sleep(1)
            if await page.locator('text="使用 手机短信验证码"').count() != 0:
                logger.info("开始短信验证码识别环节")
                await sms_recognition(page, account, mode)

            # 进行手机语音验证识别
            if await page.locator('div#header .text-header:has-text("手机语音验证")').count() > 0:
                logger.info("检测到手机语音验证页面,开始识别")
                await voice_verification(page, account, mode)

            # 检查警告,如账号存在风险或账密不正确等
            notice_type, notice_msg = await check_login_notice(page)
            if notice_type and mysql_manager:
                # 根据错误类型更新账号状态
                if notice_type == AccountStatus.banned:
                    # 账号存在风险被禁用
                    mysql_manager.update_account_status(account.username, notice_type)
                    logger.error(f"账号 {account.username} 存在风险，已更新状态为已封禁")
                elif notice_type == AccountStatus.password_error:
                    # 密码错误
                    mysql_manager.update_account_status(account.username, notice_type)
                    logger.error(f"账号 {account.username} 密码错误，已更新状态")
                else:
                    # 其他未知错误，也标记为有问题
                    mysql_manager.update_account_status(account.username, notice_type)
                    logger.error(f"账号 {account.username} 发生未知错误: {notice_msg}")

                # 错误情况下直接返回None
                return None

        # 等待验证码通过
        logger.info("等待获取cookie...")
        await page.wait_for_selector('.user', state='visible', timeout=120000)

        cookies = await context.cookies()

        # 需要的cookie字段
        required_cookies = {"pin": None, "3AB9D23F7A4B3CSS": None, "flash": None, "__jda": None, "__jdu": None,
                            "ipLoc-djd": None, "shshshfpx": None, "x-rp-evtoken": None}
        cookie_dict = {}

        # 从所有cookie中提取需要的字段
        for cookie in cookies:
            if cookie['name'] in required_cookies:
                cookie_dict[cookie['name']] = cookie['value']

        # 检查是否获取到所有必要的cookie字段
        required_fields = jd_tools.required_cookie_fields
        missing_fields = [field for field in required_fields if field not in cookie_dict]
        if missing_fields:
            logger.warning(f"未获取到所有必要的cookie字段，当前获取到: {list(cookie_dict.keys())}")
            logger.warning(f"缺少的cookie字段: {missing_fields}")
            # 记录所有获取到的cookie，便于调试
            # logger.debug(f"获取到的所有cookie: {[c['name'] for c in cookies]}")

        # 组合cookie字符串
        if cookie_dict:
            cookie_string = "; ".join([f"{name}={value}" for name, value in cookie_dict.items()])
            logger.info(f"成功获取cookie: {cookie_string[:30]}...")

            return cookie_string

        return None

    except Exception as e:
        traceback.print_exc()
        return None

    finally:
        await context.close()
        await browser.close()


async def auto_move_slide_pc(page, slider_selector, retry_times: int = 2, move_solve_type: str = ""):
    """
    自动识别移动滑块验证码
    """
    # move_solve_type = "old"
    for i in range(retry_times):
        logger.info(f'第{i + 1}次尝试自动移动滑块中...')
        # 获取 src 属性
        small_src = await page.locator('.JDJRV-smallimg img').get_attribute('src')
        background_src = await page.locator('.JDJRV-bigimg img').get_attribute('src')

        # 获取MD5编码
        small_src_md5 = get_md5(small_src)
        background_src_md5 = get_md5(background_src)

        # 获取 bytes
        small_img_bytes = get_img_bytes(small_src)
        background_img_bytes = get_img_bytes(background_src)

        # 保存小图
        small_img_path = save_img(small_src_md5, small_img_bytes)  # 使用MD5作为文件名
        small_img_width = await page.evaluate(
            '() => { return document.getElementsByClassName("JDJRV-smallimg")[0].getElementsByTagName("img")[0].clientWidth; }')  # 获取网页的图片尺寸
        small_img_height = await page.evaluate(
            '() => { return document.getElementsByClassName("JDJRV-smallimg")[0].getElementsByTagName("img")[0].clientHeight; }')  # 获取网页的图片尺寸
        small_image = Image.open(small_img_path)  # 打开图像
        resized_small_image = small_image.resize((small_img_width, small_img_height))  # 调整图像尺寸
        resized_small_image.save(small_img_path)  # 保存调整后的图像

        # 保存大图
        background_img_path = save_img(background_src_md5, background_img_bytes)
        background_img_width = await page.evaluate(
            '() => { return document.getElementsByClassName("JDJRV-bigimg")[0]'
            '.getElementsByTagName("img")[0].clientWidth; }')  # 获取网页的图片尺寸
        background_img_height = await page.evaluate(
            '() => { return document.getElementsByClassName("JDJRV-bigimg")[0]'
            '.getElementsByTagName("img")[0].clientHeight; }')  # 获取网页的图片尺寸
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
        try:
            # 查找小图
            await page.wait_for_selector(PcLoginSelectors.slider_image_selector, state='visible', timeout=3000)
        except Exception as e:
            # 未找到元素，认为成功，退出循环
            logger.info('未找到小图,认为成功,退出移动滑块')
            break


async def auto_move_slide_v2(page, retry_times: int = 2,
                             move_solve_type: str = ""):
    slider_selector = PcLoginSelectors.slider_btn_selector
    captcha_selector = PcLoginSelectors.captcha_selector
    login_selector = PcLoginSelectors.login_selector

    for i in range(retry_times):
        logger.info(f'第{i + 1}次开启滑块验证')
        # 查找小图
        try:
            # 查找小图
            await page.wait_for_selector(captcha_selector, state='visible', timeout=3000)
        except Exception as e:
            logger.info('未找到验证码框, 退出滑块验证')
            return
        await auto_move_slide_pc(page, slider_selector, retry_times=5, move_solve_type=move_solve_type)

        # 判断是否一次过了滑块
        captcha_drop_visible = await page.is_visible(captcha_selector)

        # 存在就重新滑一次
        if captcha_drop_visible:
            if i == retry_times - 1:
                return
            logger.info('一次过滑块失败, 再次尝试滑块验证')
            await page.wait_for_selector(captcha_selector, state='visible', timeout=3000)
            # 点外键
            sign_locator = page.locator('#header').locator('.text-header')
            sign_locator_box = await sign_locator.bounding_box()
            sign_locator_left_x = sign_locator_box['x']
            sign_locator_left_y = sign_locator_box['y']
            await page.mouse.click(sign_locator_left_x, sign_locator_left_y)
            await asyncio.sleep(1)
            # 提交键
            submit_locator = page.locator(login_selector)
            await submit_locator.click()
            await asyncio.sleep(1)
            continue
        return


# todo 适配pc版
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

        # 这里是文字验证码了 todo 适配PC版的文字验证码
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


async def voice_verification(page, account: Account, mode):
    '''
     todo 实现pc版的语音验证
    '''
    # 优先使用用户自己的配置
    voice_func = account.voice_func

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


async def check_login_notice(page):
    notice_type = None
    notice_msg = None
    try:
        logger.info("检查登录是否报错")
        # 检查第一种错误信息元素
        msg_error_visible = await page.locator('.msg-error').is_visible()
        if msg_error_visible:
            notice_msg = await page.locator('.msg-error').text_content()
            logger.info(f"检测到错误信息: {notice_msg}")

        # 如果第一种没有，检查第二种错误信息元素
        if not notice_msg:
            tip_title_visible = await page.locator('.tip-title').is_visible()
            if tip_title_visible and "为确认是您本人操作，请选择以下任一方式进行身份认证" not in await page.locator('.tip-title').text_content():
                notice_msg = await page.locator('.tip-title').text_content()
                logger.info(f"检测到提示信息: {notice_msg}")

        # 根据错误信息内容设置notice_type
        if notice_msg:
            if "账号名与密码不匹配" in notice_msg:
                notice_type = AccountStatus.password_error
                logger.error("账号密码错误")
            elif "风险" in notice_msg:
                notice_type = AccountStatus.banned
                logger.error("账号存在风险，可能被禁用")
            else:
                notice_type = "unknown_error"
                logger.error(f"未知错误: {notice_msg}")

            return notice_type, notice_msg
        else:
            return notice_type, notice_msg
    except TimeoutError:
        logger.info("登录未发现报错")
        return None, None


async def sms_recognition(page, account: Account, mode):
    """
    短信验证码识别
    """
    try:
        from config import sms_func, sms_webhook
    except ImportError:
        sms_func = SmsFunc.redis
        sms_webhook = ""

    # 优先使用用户自己的配置
    sms_func = account.sms_func if account.sms_func else sms_func

    # 如果是cron模式，且sms_func为manual_input，则使用redis
    if mode == RunMode.cron and sms_func == SmsFunc.manual_input:
        sms_func = SmsFunc.redis

    # 检查是否有短信验证按钮，如果有则点击
    try:
        sms_button = page.locator("button.btn-def.btn-xl.mb20:has-text('使用 手机短信验证码')")
        if await sms_button.count() > 0:
            logger.info("点击使用手机短信验证码按钮")
            await sms_button.click()
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"点击短信验证按钮失败: {e}")

    # 等待短信验证码输入框出现
    try:
        # 等待验证码输入框出现
        await page.wait_for_selector("input.field[placeholder='请输入手机验证码']", timeout=1000)

        # 点击获取短信验证码按钮
        sms_button = page.locator("button.btn-def.btn-msg.btn-l")
        if await sms_button.count() > 0:
            logger.info("点击获取短信验证码按钮")
            await sms_button.click()
            await asyncio.sleep(1)
    except TimeoutError:
        logger.info("没有触发短信验证码")
        return False

    logger.info("触发短信验证码")
    if sms_func == SmsFunc.manual_input:
        try:
            from inputimeout import inputimeout, TimeoutOccurred
            verification_code = inputimeout(prompt='请输入短信验证码: ', timeout=60)
            if not is_valid_verification_code(verification_code):
                logger.error("验证码格式错误")
                return False
        except TimeoutOccurred:
            logger.error("验证码输入超时")
            return False

    elif sms_func == SmsFunc.webhook:
        # 优先使用用户自己的配置
        sms_webhook = account.sms_webhook if account.sms_webhook else sms_webhook
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
    elif sms_func == SmsFunc.redis:
        # 从Redis获取验证码
        redis_manager = RedisManager()
        redis_key = f"{Enterprise.jd}_{account.phone}"
        retry_count = 20  # 默认重试20次

        logger.info(f"等待从Redis获取验证码，键名: {redis_key}")
        verification_code = None

        for i in range(retry_count):
            try:
                verification_code = redis_manager.redis_client.get(redis_key)
                if verification_code:
                    logger.info(f"成功从Redis获取到验证码: {verification_code},尝试次数:{i}")
                    # 获取到验证码后立即删除该key，确保验证码失效
                    redis_manager.redis_client.delete(redis_key)
                    break
                else:
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"redis服务异常：{e}")
                await asyncio.sleep(5)

        if not verification_code:
            logger.error(f"在{retry_count}次尝试后未能从Redis获取有效验证码")
            return False

    else:
        logger.error(f"不支持的短信验证码识别方式：{sms_func}")
        return False

    # 输入验证码
    await page.fill("input[type='text']", verification_code)
    # 点击提交认证按钮
    await page.click("button.btn-primary.btn-m")
    return True
