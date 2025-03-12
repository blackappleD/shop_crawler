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
- 配置config.py,
  配置文件说明请转向 [配置文件说明](https://github.com/icepage/AutoUpdateJdCookie/blob/main/配置文件说明.md)
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
- 配置config.py,
  配置文件说明请转向 [配置文件说明](https://github.com/icepage/AutoUpdateJdCookie/blob/main/配置文件说明.md)

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

#### 4. 运行方式

配置完成后，运行方式与之前相同：

```bash
# 单次执行
python main.py

# 或者使用定时任务
python schedule_main.py
```

#### 5. 新功能：Redis为空时自动初始化所有账号

### 电商数据采集

支持的网站：暂时只支持京东，后续也会接入支持其他电商平台

### 参数定义

search_url=https://search.jd.com/Search?keyword={{keyword}}
detail_url=https://item.jd.com/{{sku}}.html
login_url=https://passport.jd.com/new/login.aspx

need_login_xml=<a href="javascript:login();" class="link-login"><span>你好，</span><span class="style-red">
请登录</span></a>

sku_xml=<ul class="gl-warp clearfix" data-tpl="1"><li data-sku="100014366815" data-spu="100014366815" ware-type="10" bybt="0" class="gl-item"></li><li data-sku="100048306268" data-spu="100048306268" ware-type="10" bybt="0" class="gl-item"></ul>

title_xml=<div class="sku-name"><img src="//img13.360buyimg.com/imagetools/jfs/t1/248227/2/26957/4011/6752d75cF80d258af/b01578d43f78670c.png" id="bgIcon" style="height:16px;display:none" alt="国家补贴"><img src="//img13.360buyimg.com/imagetools/jfs/t1/84452/25/26900/1090/66bc16cbF1e47fb52/30d3a11007fd979a.png" alt="新品">
CHIYINNB【官网直营正品丨降噪Air4代】 华强北蓝牙耳机真无线适配苹果ANC降噪半入耳式iPhone16/15Pods 【原版正装全功能顶配版】
主动降噪+空间音頻</div>

price_xml=<span class="p-price msbtPrice"><span>￥</span><span class="price J-p-10128414207655">
128.00</span><span id="J_JdContent">补贴价</span></span>

img_xml=<div class="sku-name"><img src="//img13.360buyimg.com/imagetools/jfs/t1/248227/2/26957/4011/6752d75cF80d258af/b01578d43f78670c.png" id="bgIcon" style="height:16px;display:none" alt="国家补贴"><img src="//img13.360buyimg.com/imagetools/jfs/t1/84452/25/26900/1090/66bc16cbF1e47fb52/30d3a11007fd979a.png" alt="新品">
CHIYINNB【官网直营正品丨降噪Air4代】 华强北蓝牙耳机真无线适配苹果ANC降噪半入耳式iPhone16/15Pods 【原版正装全功能顶配版】
主动降噪+空间音頻</div>

### 提供Http接口

1. product_search接口
   用来根据商品关键字查询商品sku列表。爬取{{search_url}}

- parma1: keyword
- param2: page

- result: shu数组

2. product_detail接口
   用来根据商品sku获取商品详细信息，暂时只获取商品标题和价格。爬取{{detail_url}}

- param1: sku

- result: {
  "title": "xxx",
  "price": "100",
  "img": "xxx"
  }

###主要技术栈
playwright，BeautifulSoup
注意，设置浏览器参数时，尽量保证不要让服务器察觉到是爬虫

###主要流程
第一步. 使用db_manager.py中的方法从Redis中随机获取一个Cookie，
第二步. 使用playwright，当调用product_search方法时，请求{{seartch_url}}，调用product_detail方法时，请求{{detail_url}}
第三步. 等待页面加载完成后，
判断是否存在元素{{need_login_xml}}
- 如果存在，则重新获取一个不同的cookie 并回到第二步继续执行
- 如果不存在则执行第四步
第四步. 如果调用的是product_search接口： 根据{{sku_selector}}采集sku列表
如果调用的是product_detail接口： 根据{{title_xml}}爬取商品标题，根据{{price_xml}}爬取商品价格，根据{{img_xml}}爬取商品图片

