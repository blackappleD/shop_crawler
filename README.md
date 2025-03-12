# aujc

## 介绍
- 用来自动化更新青龙面板的失效JD_COOKIE, 主要有三步
    - 自动检测并获取青龙面板的失效JD_COOKIE;
    - 拿到失效JD_COOKIE内容后, 根据配置的账号信息, 自动化登录JD页面, 拿到key;
    - 根据拿到的key, 自动化更新青龙面板的失效JD_COOKIE。
- 支持的验证码类型有：
  - 滑块验证码;
  - 形状颜色验证码(基本不会出现了);
  - 点选验证码;
  - 短信验证码,支持手动输入和webhook(首次登录大概率出现, 其它时间出现频率低。webhook配置流程繁琐, 不爱折腾的建议使用手动输入或关闭。)
  - 手机语音识别验证码
- 支持的账号类型有：
  - 账号密码登录
  - QQ登录
- python >= 3.9 (playwright依赖的typing，在3.7和3.8会报错typing.NoReturn的BUG)
- 支持windows,linux(无GUI)
- 支持docker部署
- 支持代理
- linux无GUI使用文档请转向 [linux无GUI使用文档](https://github.com/icepage/AutoUpdateJdCookie/blob/main/README.linux.md)
- WINDOWS整体效果如下图

![GIF](./img/main.gif)


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
- 2种场景下需要手动
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

## 特别感谢
- 感谢 [所有赞助本项目的热心网友 --> 打赏名单](https://github.com/icepage/AutoUpdateJdCookie/wiki/%E6%89%93%E8%B5%8F%E5%90%8D%E5%8D%95)
- 感谢 **https://github.com/sml2h3/ddddocr** 项目，牛逼项目
- 感谢 **https://github.com/zzhjj/svjdck** 项目，牛逼项目

## 创作不易，如果项目有帮助到你，大佬点个星或打个赏吧
![JPG](./img/w.jpg)

## 数据源更新 (2025年3月6日更新)
为了更灵活地支持不同的数据源，我们在本次更新中添加了Redis和MySQL数据源支持：

### 1. 数据源配置
现在可以通过配置文件中的以下参数来选择数据源类型：
```python
# 数据源配置
# 账号信息来源: "config" 表示从config.py的user_datas获取，"mysql" 表示从MySQL获取
account_source = "config"  # 或 "mysql"
# Cookie来源: "qinglong" 表示从青龙面板获取，"redis" 表示从Redis获取
cookie_source = "qinglong"  # 或 "redis"
# Cookie目标存储: "qinglong" 表示存储到青龙面板，"redis" 表示存储到Redis
cookie_target = "qinglong"  # 或 "redis"
```

### 2. MySQL配置
当选择MySQL作为账号信息来源时，需要配置以下参数：
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

MySQL数据库中需要有一个名为`jd_account`的表，包含以下字段：
- `username`：用户名/账号
- `password`：密码
- `phone`：手机号

### 3. Redis配置
当选择Redis作为Cookie来源或目标存储时，需要配置以下参数：
```python
# Redis配置
redis_config = {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0,
    "password": None
}
```

### 4. 使用方式
- 如果要从MySQL获取账号信息，将`account_source`设置为`"mysql"`
- 如果要从Redis获取Cookie，将`cookie_source`设置为`"redis"`
- 如果要将更新后的Cookie存储到Redis，将`cookie_target`设置为`"redis"`

可以根据需要灵活组合这些选项，例如：
- 从配置文件获取账号信息，从Redis获取Cookie，并将更新后的Cookie存储到Redis
- 从MySQL获取账号信息，从青龙面板获取Cookie，并将更新后的Cookie存储到青龙面板
- 从MySQL获取账号信息，从Redis获取Cookie，并将更新后的Cookie存回Redis

### 5. 新功能：Redis为空时自动初始化所有账号
