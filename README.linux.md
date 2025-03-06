# linux无GUI使用文档

## 介绍
- 作者认为要用LINUX就用无GUI的，所以未对GUI版本进行测试。
- 主要的卡点在于短信验证码识别，目前支持了，所以可以LINUX上运行。
- 使用手动输入验证码方式进行登录，整体过程如下图
- 支持docker部署
- 支持的账号类型有：
  - 账号密码登录
  - QQ登录
- 支持代理
![PNG](./img/linux.png)


## 使用文档
## 1、docker部署(推荐)

### 下载镜像
```shell
docker pull icepage/aujc:latest
```

### 配置config.py
- 下载本项目的config_example.py, 重命名为config.py; 
- 配置config.py, 配置文件说明请转向 [配置文件说明](https://github.com/icepage/AutoUpdateJdCookie/blob/main/配置文件说明.md)
- config.py的**cron_expression**参数必填;
- config.py的**headless一定要设为True!!!!**

### 手动执行
- 2种场景下需要手动main.py
  - 1、需要短信验证时需要手动, 本应用在新设备首次更新时必现. 
  - 2、定时时间外需要执行脚本. 
- 配置中的sms_func设为manual_input时, 才能在终端填入短信验证码。
- 当需要手动输入验证码时, docker运行需加-i参数。否则在触发短信验证码时会报错Operation not permitted
```bash
docker run -i -v $PWD/config.py:/app/config.py icepage/aujc:latest python main.py
```

![PNG](./img/linux.png)

### 长期运行
- 程序读config.py中的cron_expression, 定期进行更新任务
- 当sms_func设置为manual_input, 长期运行时会自动将manual_input转成no，避免滥发短信验证码, 因为没地方可填验证码. 
```bash
docker run -v $PWD/config.py:/app/config.py icepage/aujc:latest
```

## 2、本地部署
### 安装依赖
```commandline
pip install -r requirements.txt
```

### 安装浏览器驱动
```commandline
playwright install-deps
```

### 安装chromium插件
```commandline
playwright install chromium
```

### 添加配置config.py
- 复制config_example.py, 重命名为config.py, 我们基于这个config.py运行程序;
- 配置config.py, 配置文件说明请转向 [配置文件说明](https://github.com/icepage/AutoUpdateJdCookie/blob/main/配置文件说明.md)

### 运行脚本
#### 1、单次手动执行
```commandline
python main.py
```

#### 2、常驻进程
进程会读取config.py里的cron_expression,定期进行更新任务
```commandline
python schedule_main.py
```

### 3、定时任务
使用crontab. 模式定为cron, 会自动将短信配置为manual_input转成no，避免滥发短信验证码.
```commandline
0 3,4 * * * python main.py --mode cron
```



### 2025年3月6日更新
1. 添加Redis和Mysql数据源
2. 修改代码块，修改mian.py中的代码，需要检测的cooKie来源切换成Redis（之前是从qinglong的环境变量中获取），将账号获取来源切换为Mysql（之前是以配置文件的方式加载）
3. 更新完cookie之后，将cookie存回redis中

### 相关配置
#### 1. 选择不同的数据源
在config.py中增加以下配置参数：
```python
# 数据源配置
# 账号信息来源: "config" 表示从config.py的user_datas获取，"mysql" 表示从MySQL获取
account_source = "mysql"  # 从MySQL获取账号信息
# Cookie来源: "qinglong" 表示从青龙面板获取，"redis" 表示从Redis获取
cookie_source = "redis"  # 从Redis获取Cookie
# Cookie目标存储: "qinglong" 表示存储到青龙面板，"redis" 表示存储到Redis
cookie_target = "redis"  # Cookie更新后存储到Redis
```

#### 2. MySQL配置
- url：127.0.0.1:3306/commodity_crawler
- username: root
- password: P@ssW0rd1874

在config.py中添加以下配置：
```python
# MySQL配置
mysql_config = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "P@ssW0rd1874",
    "database": "commodity_crawler"
}
```

账号信息存储在Mysql表jd_account中，字段为username，password，phone

#### 3. Redis配置
- url: 127.0.0.1:6379

在config.py中添加以下配置：
```python
# Redis配置
redis_config = {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0,
    "password": None
}
```

Cookie在Redis中存储类型为Hash，键值为：JD_COOKIE_MAP，其中key为 username, value为 cookie值

#### 4. 运行方式
配置完成后，运行方式与之前相同：
```bash
# 单次执行
python main.py

# 或者使用定时任务
python schedule_main.py
```

#### 5. 新功能：Redis为空时自动初始化所有账号
当选择Redis作为Cookie来源（`cookie_source = "redis"`）时，系统会自动检测Redis中的JD_COOKIE_MAP是否为空。如果为空，则会自动对所有账号进行登录并将获取的Cookie存储到目标位置（Redis或青龙面板）。

这个功能特别适用于以下场景：
- 首次设置Redis作为数据源时
- Redis数据丢失需要重新初始化所有账号Cookie
- 批量更新所有账号Cookie


