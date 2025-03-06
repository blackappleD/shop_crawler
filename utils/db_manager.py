import redis
import pymysql
from pymysql.cursors import DictCursor
from loguru import logger


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
        self.cookie_key = "JD_COOKIE_MAP"  # Redis中存储Cookie的Hash键
        
    def get_all_cookies(self):
        """
        获取所有Cookie
        
        Returns:
            dict: 用户名与Cookie的映射字典
        """
        try:
            return self.redis_client.hgetall(self.cookie_key)
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
            return self.redis_client.hget(self.cookie_key, username)
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
            self.redis_client.hset(self.cookie_key, username, cookie)
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
            self.redis_client.hdel(self.cookie_key, username)
            return True
        except Exception as e:
            logger.error(f"从Redis删除用户 {username} 的Cookie失败: {e}")
            return False


class MysqlManager:
    """MySQL管理类，用于获取JD账号信息"""
    
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
        
    def get_all_accounts(self):
        """
        获取所有JD账号信息
        
        Returns:
            list: 包含所有账号信息的列表
        """
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT username, password, phone FROM jd_account WHERE status = 1 "
                cursor.execute(sql)
                results = cursor.fetchall()
                return results
        except Exception as e:
            logger.error(f"从MySQL获取账号信息失败: {e}")
            return []
            
    def get_account(self, username):
        """
        获取指定用户的账号信息
        
        Args:
            username: 用户名
            
        Returns:
            dict: 用户账号信息，如果不存在则返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT username, password, phone FROM jd_account WHERE username = %s"
                cursor.execute(sql, (username,))
                result = cursor.fetchone()
                return result
        except Exception as e:
            logger.error(f"从MySQL获取用户 {username} 的账号信息失败: {e}")
            return None
            
    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close() 