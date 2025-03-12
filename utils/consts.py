# 项目名
program = "shop_crawler"
# JD pc登录页
jd_login_url = "https://passport.jd.com/uc/login?ltype=logout&ReturnUrl=https%3A%2F%2Fhome.jd.com%2Findex.html"
# JD mobile登录页
# jd_login_url = "https://plogin.m.jd.com/login/login?appid=300&returnurl=https%3A%2F%2Fwq.jd.com%2Fpassport%2FLoginRedirect%3Fstate%3D1103073577433%26returnurl%3Dhttps%253A%252F%252Fhome.m.jd.com%252FmyJd%252Fhome.action&source=wq_passport"

# 支持的形状类型
supported_types = [
    "三角形",
    "正方形",
    "长方形",
    "五角星",
    "六边形",
    "圆形",
    "梯形",
    "圆环"
]

# 定义了支持的每种颜色的 HSV 范围
supported_colors = {
    '紫色': ([125, 50, 50], [145, 255, 255]),
    '灰色': ([0, 0, 50], [180, 50, 255]),
    '粉色': ([160, 50, 50], [180, 255, 255]),
    '蓝色': ([100, 50, 50], [130, 255, 255]),
    '绿色': ([40, 50, 50], [80, 255, 255]),
    '橙色': ([10, 50, 50], [25, 255, 255]),
    '黄色': ([25, 50, 50], [35, 255, 255]),
    '红色': ([0, 50, 50], [10, 255, 255])
}
supported_sms_func = [
    "no",
    "webhook",
    "manual_input"
]
supported_voice_func = [
    "no",
    "manual_input"
]


class PcLoginSelectors:
    slider_btn_selector = ".JDJRV-slide-inner.JDJRV-slide-btn"
    slider_image_selector = ".JDJRV-smallimg"
    captcha_selector = ".JDJRV-suspend-slide"
    login_selector = "#loginsubmit"


class MobileLoginSelectors:
    slider_btn_selector = "img.move-img"
    slider_image_selector = "#small_img"
    captcha_selector = ".captcha_drop"
    login_selector = ".btn.J_ping.active"


class SmsFunc:
    manual_input = "manual_input"
    webhook = "webhook"
    redis = "redis"


class RunMode:
    cron = "cron"


class Platform:
    pc = "pc"
    mobile = "mobile"


class Enterprise:
    jd = "jd"
    all = "all"


class UserType:
    qq = "qq"
    acc = "acc"


class AccountStatus:
    banned = "banned"
    password_error = "password_error"
    normal = "normal"


class Account:
    id: int
    username: str
    password: str
    phone: str
    enable: bool
    user_type: str
    force_update: bool
    enterprise: str
    sms_func: str
    sms_webhook: str
    voice_func: str

    def __init__(self, username: str, password: str = "", phone: str = "",
                 enable: bool = True, status: str = AccountStatus.normal, user_type: str = UserType.acc
                 , force_update: bool = False,
                 enterprise: str = Enterprise.jd, sms_func: str = "manual_input",
                 sms_webhook: str = "https://127.0.0.1:3000/getCode",
                 voice_func: str = "no",
                 id: int = None):
        """
        初始化账号对象
        
        Args:
            username: 用户名
            password: 密码
            phone: 手机号
            enable: 账号状态，True为启用，False为禁用
            user_type: 用户类型，如"normal"、"qq"等
            is_banned: 是否被封禁
            force_update: 是否强制更新Cookie
            enterprise: 企业类型，如"jd"
            sms_func: 短信验证码功能，默认为"manual_input"
            id: 账号ID
        """
        self.id = id
        self.username = username
        self.password = password
        self.phone = phone
        self.enable = enable
        self.status = status
        self.user_type = user_type
        self.force_update = force_update
        self.enterprise = enterprise
        self.sms_func = sms_func
        self.sms_webhook = sms_webhook
        self.voice_func = voice_func


# 默认的UA, 可以在config.py里配置
user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 '
              'Safari/537.36')
