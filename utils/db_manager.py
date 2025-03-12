import redis
import pymysql
import random
from pymysql.cursors import DictCursor
from loguru import logger

from jd.jd_tools import CookieMapRedisKey
from utils.consts import Enterprise, AccountStatus


class RedisManager:
    """Redis管理类，用于操作Redis中的JD_COOKIE"""

    def __init__(self, host='127.0.0.1', port=6379, db=0, password=None):
        """
        初始化Redis连接
        
        Args:
            host: Redis服务器地址
            port: Redis服务器端口
            db: Redis数据库索引
            password: Redis密码
        """
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True  # 自动将字节解码为字符串
        )
        # todo 后续更改为根据电商平台和平台类型获取redis map : JD_PC_COOKIE_MAP
        self.cookie_map_key = CookieMapRedisKey.pc  # Redis中存储Cookie的Hash键

    def get_all_cookies(self):
        """
        获取所有Cookie

        Returns:
            dict: 用户名与Cookie的映射字典
        """
        try:
            return self.redis_client.hgetall(self.cookie_map_key)
        except Exception as e:
            logger.error(f"从Redis获取Cookie失败: {e}")
            return {}

    def get_cookie(self, username):
        """
        获取指定用户的Cookie

        Args:
            username: 用户名

        Returns:
            str: 用户的Cookie，如果不存在则返回None
        """
        try:
            return self.redis_client.hget(self.cookie_map_key, username)
        except Exception as e:
            logger.error(f"从Redis获取用户 {username} 的Cookie失败: {e}")
            return None

    def set_cookie(self, username, cookie):
        """
        设置用户的Cookie
        
        Args:
            username: 用户名
            cookie: Cookie值
            
        Returns:
            bool: 是否设置成功
        """
        try:
            self.redis_client.hset(self.cookie_map_key, username, cookie)
            return True
        except Exception as e:
            logger.error(f"在Redis中设置用户 {username} 的Cookie失败: {e}")
            return False

    def delete_cookie(self, username):
        """
        删除用户的Cookie
        
        Args:
            username: 用户名
            
        Returns:
            bool: 是否删除成功
        """
        try:
            self.redis_client.hdel(self.cookie_map_key, username)
            return True
        except Exception as e:
            logger.error(f"从Redis删除用户 {username} 的Cookie失败: {e}")
            return False

    def get_random_cookie(self):
        """
        从Redis中获取一个随机的Cookie
        
        Returns:
            tuple: (username, cookie) 元组，如果没有Cookie则返回(None, None)
        """
        try:
            all_cookies = self.get_all_cookies()
            if not all_cookies:
                logger.warning("Redis中没有可用的Cookie")
                return None, None

            # 随机选择一个username和对应的cookie
            username = random.choice(list(all_cookies.keys()))
            cookie = all_cookies[username]

            logger.info(f"已随机获取用户 {username} 的Cookie")
            return username, cookie

        except Exception as e:
            logger.error(f"从Redis获取随机Cookie失败: {e}")
            return None, None


class MysqlManager:
    """MySQL管理类，用于获取账号信息"""

    def __init__(self, host='127.0.0.1', port=3306, user='root', password='', database=''):
        """
        初始化MySQL连接
        
        Args:
            host: MySQL服务器地址
            port: MySQL服务器端口
            user: MySQL用户名
            password: MySQL密码
            database: MySQL数据库名
        """
        self.connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=DictCursor
        )

    def get_all_accounts(self, enterprise):
        """
        获取所有账号信息
        
        Returns:
            list: 包含所有账号信息的列表
        """
        try:
            with (self.connection.cursor() as cursor):
                sql = "SELECT username, password, phone FROM account WHERE enable = 1 "
                if enterprise != Enterprise.all:
                    sql += " AND enterprise = %s", enterprise
                cursor.execute(sql)
                results = cursor.fetchall()
                return results
        except Exception as e:
            logger.error(f"从MySQL获取账号信息失败: {e}")
            return []

    def update_account_status(self, username, status):
        """
        更新账号状态
        
        Args:
            username: 用户名
            status: 状态，如 'banned' 或 'password_error'
            
        Returns:
            bool: 是否更新成功
        """
        try:
            with self.connection.cursor() as cursor:
                sql = "UPDATE account SET status = %s WHERE username = %s"
                if status == AccountStatus.banned:
                    sql = "UPDATE account SET status = %s, enable = 0 WHERE username = %s"
                cursor.execute(sql, (status, username))
                self.connection.commit()
                affected_rows = cursor.rowcount
                logger.info(f"更新账号 {username} 状态为 {status}，影响 {affected_rows} 行")
                return affected_rows > 0
        except Exception as e:
            logger.error(f"更新账号 {username} 状态失败: {e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
