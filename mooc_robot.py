from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.edge.service import Service as edgeService
from selenium.webdriver import Edge as edge
from selenium.webdriver.edge.options import Options as edgeOptions

from selenium.webdriver.chrome.service import Service as chromeService
from selenium.webdriver import chrome as chrome
from selenium.webdriver.chrome.options import Options as chromeOptions

from selenium.webdriver.firefox.service import Service as firefoxService
from selenium.webdriver import Firefox as firefox
from selenium.webdriver.firefox.options import Options as firefoxOptions


from selenium.webdriver.ie.service import Service as ieService
from selenium.webdriver import Ie as ie
from selenium.webdriver.ie.options import Options as ieOptions

from selenium.webdriver.safari.service import Service as safariService
from selenium.webdriver import Safari as safari
from selenium.webdriver.safari.options import Options as safariOptions

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import ElementNotInteractableException as enie
from selenium.common.exceptions import NoSuchElementException as nsee
from selenium.common.exceptions import StaleElementReferenceException as sere
from selenium.common.exceptions import WebDriverException as we

import cv2 as cv
import time
import os
import sys
import numpy as np
from openai import OpenAI
import requests
from bs4 import BeautifulSoup

print('''
------欢迎使用学习通自动登录及答案查找bot------

------使用时请先将 <_internal文件夹> 与 <mooc_robot.exe> 置于同一文件夹下, <mooc_exe> 为入口------

------本程序基于 <deepseekAPI>, 即使用时, 需自行获取 <deepseekAPI> 并输入------

------在使用时, 请确保api使用余额不为零, 否则程序无法请求api以获取答案生成------

-----------------------------------------------------------------------

------本程序拥有记忆功能, <作业地址> 及 <7日有效cookie> 及 <deepseekAPI> 将在首次获取后以txt形式保留于 <mooc_robot.exe所处文件夹> 下, 若需更改请自行从选单更改------

------注意: 本程序无自动输入功能, 用户在获取所有作业答案后, 需自行填选或输入文本内容------
      
      
''')



openai_api_key = '' #deekseekapi-key
generate_text = '' #初次访问答案
buffertime = 1 #滑块缓冲时间，视网络情况
browser_type = 'edge' #选择浏览器,默认edge于测试
driver = None
big_img_Y = 0.0 #大图高斯模糊参数
sapl_img_Y = 0.0 #小图高斯模糊参数
uname = '' #用户名
pwd = ''   #密码 

#打包成exe文件时必要的路径函数，无需更改
class FilePath:
    @staticmethod
    def resource_path(relative_path):
        try:
                # PyInstaller 创建的临时文件夹
            base_path = sys._MEIPASS
        except AttributeError:
                # 开发环境中的基础路径
            base_path = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(base_path, relative_path)




#所有用户输入数据类
class GetData:
    def __init__(self):
        pass


    def store(self, _data, _data_type):    
        data_val = ''
        with open(FilePath.resource_path(_data), 'a+') as file:
            if os.stat(FilePath.resource_path(_data)).st_size == 0:
                new_val = input(f"请输入新的{_data_type}: ")
                file.write(new_val)
                file.seek(0)
                data_val = file.read()
                return data_val
            else:
                file.seek(0)
                data_val = file.read()
                return data_val
    

    def restore(self, _data, _data_type):
        with open(FilePath.resource_path(_data), 'a+') as file:
            new_val = input(f"请输入新的{_data_type}: ")
            file.truncate(0)
            file.write(new_val)
            file.flush()
            file.seek(0)
            data_val = file.read()
            print(f'{_data_type}已更新')
            return data_val


address, cookie, openai_api_key = GetData(), GetData(), GetData() #作业地址、7日有效cookie、deepseekAPI

#自动登录，返回自动获取到的cookie
def signin():
    global driver
    def chose_driver(_browser_type = browser_type):
        global driver, browser_type, big_img_Y, sapl_img_Y 
            #判别输入是否合法
        drivers = ['edge', 'chrome', 'firefox', 'ie', 'safari']
        browser_type = input('请输入正确的浏览器类型(edge/chrome/firefox/ie/safari): ')
        while browser_type not in drivers:
            browser_type = input('请输入正确的浏览器类型(edge/chrome/firefox/ie/safari): ')     
            #选择相应浏览器驱动driver
        driver_serv = _browser_type + 'Service'
        driver_opt = _browser_type + 'Options'
            #定义变量driver为Webelement对象且指定浏览器驱动driver
        service = eval(driver_serv)(executable_path= FilePath.resource_path(f'{browser_type}Driver.exe'))
        options = eval(driver_opt)()
        if browser_type == 'safari':
            options.add_argument('--kiosk')
        else:
            options.add_argument('--start-maximized')
        driver =eval(_browser_type)(service=service, options=options)
    chose_driver()
    

    #定义获取网页cookie，无需单独执行
    def get_cookie():
        global driver
        cookies = driver.get_cookies()
        cookie_str = ''
        for cookie in cookies:
            cookie_str += cookie['name'] + '=' + cookie['value'] + '; '
        return cookie_str
    

    def valuable_setting():
        global buffertime
        buffertime = int(input("输入滑块缓冲时间(秒)，视网络情况(默认1秒): "))
            #检查buffertime输入是否合法
        while int(buffertime) > 10:
            buffertime = int(input("输入滑块缓冲时间(秒)，视网络情况(默认1秒): "))
            try:
                buffertime = int(buffertime)
            except:
                buffertime = 1

        big_img_Y = float(input("输入大图高斯模糊参数(0-5),(默认0): ")) #默认0通常无需更改
            #检查big_img_Y输入是否合法
        while float(big_img_Y) not in np.arange(0.0,5.0,0.1):
            big_img_Y = float(input("输入大图高斯模糊参数(0-5),(默认0): ")) #默认0通常无需更改
            try:
                big_img_Y = float(big_img_Y)
            except:
                big_img_Y = 1
        
        sapl_img_Y = float(input("输入小图高斯模糊参数(0-5),(默认0): ")) #默认0通常无需更改
            #检查sapl_img_Y输入是否合法
        while float(sapl_img_Y) not in np.arange(0.0,5.0,0.1):
            sapl_img_Y = float(input("输入小图高斯模糊参数(0-5),(默认0): ")) #默认0通常无需更改
            try:
                sapl_img_Y = float(sapl_img_Y)
            except:
                sapl_img_Y = 0
     
    
    #从用户取得用户名、密码
    def sign_in():
        global uname, pwd
        uname = input('请输入用户名: ')
        pwd = input('请输入密码: ')

        
    #输入用户名、密码、取得验证码、点击登录按钮
    def mous_preimg():    
        try:
            global driver, uname, pwd
            time.sleep(buffertime / 2)
            el = WebDriverWait(driver, timeout=5).until(lambda d: d.find_element(By.NAME, value='uname'))           
            _username = driver.find_element(By.NAME, value='uname')
            _username.send_keys(uname)
            _pwd = driver.find_element(By.NAME, value= 'pwd')
            _pwd.send_keys(pwd)
                #点击登录按钮
            el = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element(By.CSS_SELECTOR, value = '#login'))
            login_button = driver.find_element(By.CSS_SELECTOR, value = '#login')
            ActionChains(driver)\
            .move_to_element(login_button)\
            .click()\
            .perform()
            return True
        except Exception:
            pass
            return False
        

    #取得滑动距离
    def deal_img():    
        try:    
            global buffertime
            time.sleep(buffertime / 2)
            el = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element(By.ID, 'cx_obstacle_canvas'))
            big_img = driver.find_element(By.ID, 'cx_obstacle_canvas')
            big_img.screenshot(FilePath.resource_path("big_img.png"))

            el = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element(By.CSS_SELECTOR, 'img[draggable="false"]'))
            sapl_img = driver.find_element(By.CSS_SELECTOR, 'img[draggable="false"]')
            sapl_img.screenshot(FilePath.resource_path("sapl_img.png"))

            #绘制遮挡矩形
            def hide_sqare(_img, _pt_left_top, _pt_right_bottom):    
                #左上及右下点位
                pt_left_top = _pt_left_top
                pt_right_bottom = _pt_right_bottom
                #颜色厚度
                point_color = (255, 255 ,255)
                thickness = -1
                linetype = 4
                cv.rectangle(_img, pt_left_top, pt_right_bottom, point_color, thickness, linetype)


            big_img = cv.imread(FilePath.resource_path("big_img.png"))
            if big_img is None:
                print("错误：无法读取 big_img.png")
                return 0
            hide_sqare(big_img, (0, 0), (56, -160))
            big_img = cv.cvtColor(big_img, cv.COLOR_BGR2GRAY)
            big_img = cv.GaussianBlur(big_img, (7, 7), big_img_Y)
            _, big_imgs = cv.threshold(big_img, 127, 255, cv.THRESH_BINARY)    
            big_imgs_figures, _  = cv.findContours(big_imgs, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            
            sapl_img = cv.imread(FilePath.resource_path("sapl_img.png"))
            if sapl_img is None:
                print("错误：无法读取 sapl_img.png")
                return 0
            sapl_img = cv.cvtColor(sapl_img, cv.COLOR_BGR2GRAY)
            sapl_img = cv.GaussianBlur(sapl_img, (7, 7), sapl_img_Y)
            _, sapl_img = cv.threshold(sapl_img, 127, 255, cv.THRESH_BINARY)
            sapl_img_figures, _ = cv.findContours(sapl_img, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

            for sapl_img_figure in sapl_img_figures:
                sapl_img_edge = cv.contourArea(sapl_img_figure)
                if sapl_img_edge != 0:
                    for img in big_imgs_figures:
                        edge = cv.contourArea(img)
                        if abs(edge - sapl_img_edge) / sapl_img_edge < 0.1:
                            (x, y), rad = cv.minEnclosingCircle(img)
                            circle_center_x = x + rad
                            return int(abs(circle_center_x - 28.0))
        except Exception:
            pass
            return False
    

    #移动滑块
    def drag_mous():
        try:    
            global buffertime
            el = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element(By.CSS_SELECTOR, value = '.notSel'))
            time.sleep(buffertime / 2)
            identity = driver.find_element(By.CSS_SELECTOR, value = '.notSel')
            ActionChains(driver)\
            .move_to_element(identity)\
            .click_and_hold(identity)\
            .move_by_offset(deal_img(), 0)\
            .release()\
            .perform()
        except Exception:
            el = WebDriverWait(driver, timeout=3).until(lambda d: d.find_element(By.CSS_SELECTOR, value = '.notSel'))
            identity = driver.find_element(By.CSS_SELECTOR, value = '.notSel')
            ActionChains(driver)\
            .move_to_element(identity)\
            .click_and_hold(identity)\
            .move_by_offset(230, 0)\
            .release()\
            .perform()
        

    #验证失败
    def check_failed():
        try:
            faliedd = driver.find_element(By.CLASS_NAME, value = 'cx_hkinnerWrap_cx_error')
            return True
        except Exception:
            return False

    
    #验证进入内网
    def check_title():
        try:
            title = driver.find_element(By.XPATH, value = "//*[contains(text(), 'Title')]")
            return True
        except Exception:
            return False
        

    #验证失败刷新
    def check_retry():
        try:
            rtry = driver.find_element(By.XPATH, value = "//*[contains(text(), '失败过多，点此重试')]")
            return True
        except Exception:
            return False

    #首次滑块验证后失败重试操作
    def refresh_and_retry():
        global buffertime
        while True:
            if check_title() == True:
                break
            if check_retry() == True:
                driver.refresh()
                mous_preimg()
                deal_img()
                drag_mous()
                time.sleep(buffertime / 2)
                continue
            if check_failed() == True:
                deal_img()
                drag_mous()
                time.sleep(buffertime / 2)
                continue
            else:
                deal_img()
                drag_mous()
                time.sleep(buffertime / 2)
                continue
        return True

    
    #执行：判断是否登录成功、登录程序将不会自动关闭登录网页
    def excution():
        try:
                #打开门户网站
            driver.get('https://v8.chaoxing.com')
            sign_in()
            valuable_setting()
            mous_preimg()
            deal_img()
            drag_mous()
            time.sleep(buffertime / 2)
            if refresh_and_retry():
                print("登录成功!")
                # 刷新页面确保进入系统
                driver.refresh()
                time.sleep(buffertime / 2)
                # 获取cookie
                cookie = get_cookie()
                print(f"获取到的cookie: {cookie}")
                return cookie
        finally:
            #不关闭浏览器，保持登录状态
            pass
    
    
    return excution()


#定义 是否选择存储自动获取的cookie
def store_auto_cookie(_auto_cookie):
    with open(FilePath.resource_path('page_cookie.txt'), 'a+') as file:
        file.truncate(0)
        file.seek(0)
        file.write(_auto_cookie)


def answer():
        #取得requests库请求头
    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0',
    'Cookie': cookie.store('page_cookie.txt', 'cookie')
    }

        #取得作业网页所有内容
    src = requests.get(address.store('page_address.txt', '地址'), headers = header).text
    src_text = BeautifulSoup(src, 'html.parser')

        #记录所有文本数据
    all_works_orgns = src_text.find_all('div', attrs = {'class': "whiteDiv"})
    all_works_text = ""
    for all_work in all_works_orgns:
        all_work_text_ = all_work.text
        all_works_text += all_work_text_
    print('已读取所有文本内容')

    #使用deepseek生成答案
    def using_ds(_texts = all_works_text):
        global openai_api_key
        openai_api_key.store('deepseekapi.txt', 'deepseekAPI')
        valid_nums = ['1','2','3','4','5','6','7','8']
        user_input_orgn = ''
        user_input_orgn = input(
'''根据解题需要输入符合需求参数：
代码生成/数学解题:'1'
数据抽取/分析:'2'
通用对话:'3'
翻译:'4'
创意类写作/诗歌创作:'5'

若需重新输入地址:'6'

若需重新输入有效cookie:'7'

若需重新输入有效图片cookie:'8'

若更改api:'9'
:     ''')
        while user_input_orgn not in valid_nums:
            user_input_orgn = input(
    '''
输入数字0-7!
根据解题需要输入符合需求参数：
代码生成/数学解题:'1'
数据抽取/分析:'2'
通用对话:'3'
翻译:'4'
创意类写作/诗歌创作:'5'

若需重新输入地址:'6'

若需重新输入有效cookie:'7'

若更改api:'8'
:     ''')
        user_input = float(user_input_orgn) 
        while user_input in (6, 7, 8):
            if user_input == 6:
                address.restore('page_address.txt', '地址')
            elif user_input == 7:
                cookie.restore('page_cookie.txt', 'cookie')
            elif user_input == 8:
                openai_api_key = openai_api_key.restore('api.txt', 'api')
            user_input = float(input(
'''根据解题需要输入符合需求参数：
代码生成/数学解题:'1'
数据抽取/分析:'2'
通用对话:'3'
翻译:'4'
创意类写作/诗歌创作:'5'

若需重新输入地址:'6'

若需重新输入有效cookie:'7'

若更改api:'8'
:     '''))
        

        tempval = user_input
        model_selceting = ''
        while model_selceting not in ['1', '2']:
            model_selceting = input("请选择模式(普通模式'1'/深度思考'2'): ")
        os.system('cls')
    
        _temp = {
            1:'0.0',
            2:'1.0',
            3:'1.3',
            4:'1.3',
            5:'1.5'
        }
        
        message_ = [
            {'role': 'system', 'content': "你是一名专业的答题助手,如包含base64图片则以输入的自然顺序依次匹配文本题号及图片,直接给出答案结果。若已作答,请忽略先前作答的答案.使用中文回答所有问题."},
            {'role': 'user', 'content': _texts},    
        ]

        model_selcet = {
            '1':'deepseek-chat',
            '2':'deepseek-reasoner'
        }
        
        os.environ["OPENAI_API_KEY"] = openai_api_key
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"), base_url="https://api.deepseek.com")
        print('api请求成功')
        def generate():
            os.system('cls')
            print('正在生成...')
            response = client.chat.completions.create(
            model= model_selcet[model_selceting],
            temperature = float(_temp[tempval]),
            messages = message_,
            stream=False)
            os.environ.pop("OPENAI_API_KEY", None)
            response_str = response.choices[0].message.content
            return response_str
        return generate()
    response = using_ds()
    print(response)
    return response


#是否结束程序
def end_exe():
    close_terminal = input('输入close关闭窗口')
    if close_terminal == 'close':
        return 0
    else:
        close_terminal = input('输入close关闭窗口')


#主函数
def main():
        #是否需要自动获取cookie
    if_needed_signin = input('是否需要自动获取cookie?: ')
    while if_needed_signin not in ['', '1']:
        if_needed_signin = input('是否需要自动获取cookie?: ')
    if if_needed_signin == '1':
        auto_cookie = signin()
        store_auto_cookie(auto_cookie)
            #执行自动解析答案
    answer()
    end_exe()


if __name__ == '__main__':
    main()