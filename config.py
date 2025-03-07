# JD用户信息
user_datas = {
   
}

# ql信息
qinglong_data = {

}

# 定时器
cron_expression = "*/11 * * * *"

# 浏览器是否开启无头模式，即是否展示整个登录过程
headless = False

# 是否开启发消息
is_send_msg = False
# 更新成功后是否发消息的开关
is_send_success_msg = True
# 更新失败后是否发消息的开关
is_send_fail_msg = True
# 配置发送地址
send_info = {
    "send_wecom": [
    ],
    "send_webhook": [
    ],
    "send_dingtalk": [
    ],
    "send_feishu": [
    ],
    "send_pushplus": [
    ]
}

# sms_func为填写验信验证码的模式，有3种可选，如下：
# no 关闭短信验证码识别
# manual_input 手动在终端输入验证码
# webhook 调用api获取验证码,可实现全自动填写验证码
sms_func = "manual_input"
sms_webhook = "https://127.0.0.1:3000/getCode"

# voice_func为手机语音验证码的模式，no为关闭识别，manual_input为手动在终端输入验证码
voice_func = "manual_input"

# # 代理的配置，只代理登录，不代理请求QL面板和发消息
# proxy = {
#     # 代理服务器地址, 支持http, https, socks5
#     "server": "http://",
#     # 代理服务器账号
#     "username": "",
#     # 代理服务器密码
#     "password": ""
# }

# MySQL配置
mysql_config = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "P@ssW0rd1874",
    "database": "commodity_crawler"
}

# Redis配置
redis_config = {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0,
    "password": None  # 如果没有密码则为None
}

# 数据源配置
# 账号信息来源: "config" 表示从config.py的user_datas获取，"mysql" 表示从MySQL获取
account_source = "mysql"
# Cookie来源: "qinglong" 表示从青龙面板获取，"redis" 表示从Redis获取
cookie_source = "redis"
# Cookie目标存储: "qinglong" 表示存储到青龙面板，"redis" 表示存储到Redis
cookie_target = "redis"

# 如果需要使用MySQL和Redis作为数据源，可以使用以下配置：
# account_source = "mysql"  # 从MySQL获取账号信息
# cookie_source = "redis"   # 从Redis获取Cookie
# cookie_target = "redis"   # Cookie更新后存储到Redis