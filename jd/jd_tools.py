from typing import Union
import re


def extract_username_pc(value: str) -> Union[str, None]:
    """
    用正则提取value中pin的值, 返回一个pin,如果返回多个或没匹配上则返回空
    """
    pattern = r'pin\s*=\s*(["\']?)([^"\';]+)\1'  # 捕获pin 的值，并匹配可能的引号
    matches = re.findall(pattern, value)
    # 如果找到了多个匹配或没有匹配，则返回空
    if len(matches) == 1:
        # 返回 pin 的值
        return matches[0][1]
    return None


def extract_username_mobile(value: str) -> Union[str, None]:
    """
    用正则提取value中pin的值, 返回一个pin,如果返回多个或没匹配上则返回空
    """
    pattern = r'pt_pin\s*=\s*(["\']?)([^"\';]+)\1'  # 捕获pt_pin 的值，并匹配可能的引号
    matches = re.findall(pattern, value)
    # 如果找到了多个匹配或没有匹配，则返回空
    if len(matches) == 1:
        # 返回 pin 的值
        return matches[0][1]
    return None


required_cookie_fields = ["pin", "3AB9D23F7A4B3CSS", "flash", "__jda", "__jdu", "ipLoc-djd", "shshshfpx",
                          "x-rp-evtoken"]


class CookieMapRedisKey:
    pc = 'JD_PC_COOKIE_MAP'
    mobile = 'JD_MOBILE_COOKIE_MAP'
