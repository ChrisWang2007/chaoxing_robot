from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver import Edge
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.ie.service import Service as IeService
from selenium.webdriver import Ie
from selenium.webdriver.ie.options import Options as IeOptions
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, SessionNotCreatedException

import html as html_lib
import json
import time
import os
import re
import sys
import unicodedata
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from urllib.parse import urlparse

# 修复 Windows 控制台在 GBK 环境下打印 emoji 导致的编码错误
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SUPPORTED_BROWSERS = {
    'edge': (EdgeService, Edge, EdgeOptions),
    'chrome': (ChromeService, Chrome, ChromeOptions),
    'firefox': (FirefoxService, Firefox, FirefoxOptions),
    'ie': (IeService, Ie, IeOptions),
}
DEFAULT_BROWSER = 'edge'
DEFAULT_BUFFER_TIME = 1
DEFAULT_BLUR = 0.0
FIXED_WINDOW_SIZE = (1280, 720)
QA_EXIT_COMMANDS = {'exit', 'quit', 'q', '退出'}
QA_HISTORY_LIMIT = None  # None 表示不限制轮次
UI_WIDTH = 64
CHROMIUM_BROWSERS = {'edge', 'chrome'}
TEXT_VERIFY_TIMEOUT = 2.0
TEXT_VERIFY_INTERVAL = 0.2
UI_STATUS_PREFIX = {
    'success': '[OK]',
    'info': '[INFO]',
    'warn': '[WARN]',
    'error': '[ERR]',
    'progress': '[...]',
}

DRIVER_FILES = {
    'edge': 'edgeDriver.exe',
    'chrome': 'chromeDriver.exe',
    'firefox': 'firefoxDriver.exe',
    'ie': 'ieDriverServer.exe'
}

QUESTION_TYPE_MAP = {
    '0': '单选题',
    '1': '多选题',
    '2': '填空题',
    '3': '判断题',
    '6': '论述题',
}
TEXT_QUESTION_TYPE_VALUES = {'4', '5', '6', '7', '8', '18', '26'}
EDITOR_NOISE_TOKENS = {
    '段落格式',
    '字体',
    '字号',
    '点击上传',
    '清除格式',
    '格式刷',
    '加粗',
    '斜体',
    '下划线',
    '字体颜色',
    '缩进',
    '居左对齐',
    '居中对齐',
    '居右对齐',
    '特殊字符',
    '插入表格',
    '图片',
    '附件',
    '录音',
    '音频',
    '拍照上传',
    '画板',
    '代码块',
    '导入word',
    'x',
}


def _ui_display_width(text):
    total = 0
    for char in str(text):
        total += 2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1
    return total


def _ui_pad(text, width, align='left'):
    text = str(text)
    padding = max(width - _ui_display_width(text), 0)
    if align == 'center':
        left = padding // 2
        right = padding - left
        return ' ' * left + text + ' ' * right
    if align == 'right':
        return ' ' * padding + text
    return text + ' ' * padding


def _ui_wrap(text, width):
    text = '' if text is None else str(text)
    raw_lines = text.splitlines() or ['']
    wrapped_lines = []

    for raw_line in raw_lines:
        if not raw_line:
            wrapped_lines.append('')
            continue

        current = ''
        current_width = 0
        for char in raw_line:
            char_width = 2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1
            if current and current_width + char_width > width:
                wrapped_lines.append(current)
                current = char
                current_width = char_width
            else:
                current += char
                current_width += char_width
        if current or not wrapped_lines:
            wrapped_lines.append(current)

    return wrapped_lines or ['']


def _ui_card(title=None, lines=None, title_align='left'):
    lines = [] if lines is None else list(lines)
    print("\n┌" + "─" * UI_WIDTH + "┐")
    if title:
        print("│" + _ui_pad(title, UI_WIDTH, align=title_align) + "│")
        if lines:
            print("├" + "─" * UI_WIDTH + "┤")

    for line in lines:
        for wrapped_line in _ui_wrap(line, UI_WIDTH - 2):
            print("│ " + _ui_pad(wrapped_line, UI_WIDTH - 2) + " │")

    print("└" + "─" * UI_WIDTH + "┘")


def ui_title(title, subtitle=None, icon=None):
    heading = f"{icon} {title}" if icon else title
    lines = []
    if subtitle:
        if isinstance(subtitle, (list, tuple)):
            lines.extend(subtitle)
        else:
            lines.append(subtitle)
    _ui_card(heading, lines, title_align='center')


def ui_section(title):
    print(f"\n{title}")
    print("─" * UI_WIDTH)


def ui_status(level, message):
    prefix = UI_STATUS_PREFIX.get(level, '[INFO]')
    print(f"{prefix} {message}")


def ui_menu(title, items):
    _ui_card(title, items, title_align='left')


def ui_summary(title, rows, notes=None):
    label_width = 0
    normalized_rows = []
    for label, value in rows:
        label_text = str(label)
        value_text = str(value)
        label_width = max(label_width, _ui_display_width(label_text))
        normalized_rows.append((label_text, value_text))

    lines = [
        f"{_ui_pad(label, label_width)} : {value}"
        for label, value in normalized_rows
    ]
    if notes:
        if isinstance(notes, (list, tuple)):
            lines.extend(notes)
        else:
            lines.append(notes)
    _ui_card(title, lines, title_align='left')


def ui_block(content, indent='  '):
    if content is None:
        return

    lines = content if isinstance(content, (list, tuple)) else str(content).splitlines()
    lines = lines or ['']
    for line in lines:
        if line == '':
            print('')
        else:
            print(f"{indent}{line}")


def ui_prompt(message):
    return f"[INPUT] {message}"


def get_available_browsers():
    """检测可用的浏览器驱动"""
    available = []
    missing = []
    for browser, driver_name in DRIVER_FILES.items():
        driver_path = FilePath.resource_path(driver_name)
        if os.path.exists(driver_path):
            available.append(browser)
        else:
            missing.append(browser)
    return available, missing


def print_browser_driver_status():
    """打印浏览器驱动状态，并允许用户动态添加驱动"""
    while True:
        available, missing = get_available_browsers()
        ui_title('浏览器驱动检查', subtitle='Windows')

        if available:
            ui_status('success', f"检测到可用驱动: {', '.join(available)}")
            ui_status('info', '可以直接使用自动登录功能。')
            break
        else:
            ui_status('error', '未检测到任何浏览器驱动文件。')
            ui_section('请将以下驱动文件之一放入程序目录')
            ui_block([
                f"{browser.upper():<8} {driver_file}"
                for browser, driver_file in DRIVER_FILES.items()
            ])
            ui_section('下载地址')
            ui_block([
                'Edge   : https://developer.microsoft.com/microsoft-edge/tools/webdriver/',
                'Chrome : https://chromedriver.chromium.org/downloads',
                'Firefox: https://github.com/mozilla/geckodriver/releases',
                'IE     : https://www.selenium.dev/downloads/',
            ])
            ui_status('info', "添加驱动后按回车重新检测，或输入 'skip' 跳过，或输入目录路径。")
            
            try:
                choice = input(ui_prompt("按回车重新检测，输入 'skip' 跳过，或输入目录路径: ")).strip()
                if choice.lower() == 'skip':
                    ui_status('info', '跳过驱动检测，你仍可以使用解题功能。')
                    break
                elif choice and os.path.isdir(choice):
                    FilePath.custom_driver_path = choice
                    ui_status('success', f'已设置自定义驱动路径: {choice}')
                    # 重新检测
                    continue
                elif choice:
                    ui_status('warn', '输入的路径不存在或不是目录，请重新输入。')
                    continue
                # 空输入，继续循环重新检测
            except (EOFError, KeyboardInterrupt):
                ui_status('info', '检测已跳过，继续运行程序...')
                break


class FilePath:
    custom_driver_path = None  # 用户自定义驱动路径
    
    def __init__(self):
        """初始化文件路径"""
        try:
            self.base_path = sys._MEIPASS
        except AttributeError:
            self.base_path = os.path.abspath(os.path.dirname(__file__))

    @staticmethod
    def script_dir():
        return os.path.abspath(os.path.dirname(__file__))

    @staticmethod
    def executable_dir():
        try:
            return os.path.abspath(os.path.dirname(sys.executable))
        except (AttributeError, NameError):
            return FilePath.script_dir()

    @staticmethod
    def is_frozen():
        return bool(getattr(sys, 'frozen', False))

    @staticmethod
    def driver_path(relative_path):
        # 优先检查用户自定义路径
        if FilePath.custom_driver_path and os.path.exists(os.path.join(FilePath.custom_driver_path, relative_path)):
            return os.path.join(FilePath.custom_driver_path, relative_path)
        
        # 检查PyInstaller临时目录
        try:
            base_path = sys._MEIPASS
            path = os.path.join(base_path, relative_path)
            if os.path.exists(path):
                return path
        except AttributeError:
            pass
        
        # 检查exe文件所在目录
        try:
            exe_dir = os.path.dirname(sys.executable)
            path = os.path.join(exe_dir, relative_path)
            if os.path.exists(path):
                return path
        except (AttributeError, NameError):
            pass
        
        # 检查脚本目录
        return os.path.join(FilePath.script_dir(), relative_path)

    @staticmethod
    def config_path(relative_path):
        base_dir = FilePath.executable_dir() if FilePath.is_frozen() else FilePath.script_dir()
        return os.path.join(base_dir, relative_path)

    @staticmethod
    def resource_path(relative_path):
        return FilePath.driver_path(relative_path)
    
    @property
    def page_address_file(self):
        """获取作业地址文件路径"""
        from pathlib import Path
        return Path(self.config_path('page_address.txt'))
    
    @property
    def page_cookie_file(self):
        """获取 Cookie 文件路径"""
        from pathlib import Path
        return Path(self.config_path('page_cookie.txt'))
    
    @property
    def api_key_file(self):
        """获取 API 密钥文件路径"""
        from pathlib import Path
        return Path(self.config_path('api.txt'))


class SimpleStore:
    def __init__(self, filename, prompt_name):
        self.path = FilePath.config_path(filename)
        self.prompt_name = prompt_name

    def read(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return ''
        with open(self.path, 'r', encoding='utf-8') as file:
            return file.read().lstrip('\ufeff').strip()

    def write(self, value):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as file:
            file.write(str(value).strip())

    def get_or_prompt(self):
        value = self.read()
        if value:
            return value
        value = input(ui_prompt(f'请输入新的{self.prompt_name}: ')).strip()
        self.write(value)
        return value

    def update(self):
        value = input(ui_prompt(f'请输入新的{self.prompt_name}: ')).strip()
        if not value:
            ui_status('info', f'{self.prompt_name}未更改。')
            return
        self.write(value)
        ui_status('success', f'{self.prompt_name}已更新。')
        return value


address_store = SimpleStore('page_address.txt', '地址')
cookie_store = SimpleStore('page_cookie.txt', 'cookie')
api_store = SimpleStore('api.txt', 'api')


def choose_browser():
    ui_menu('选择浏览器类型', [
        '1. Edge (推荐)',
        '2. Chrome',
        '3. Firefox',
        '4. IE',
    ])

    browser_map = {'1': 'edge', '2': 'chrome', '3': 'firefox', '4': 'ie'}
    choice = input(ui_prompt('请输入选择 (1-4): ')).strip()

    while choice not in browser_map:
        choice = input(ui_prompt('无效选择，请输入 1-4: ')).strip()

    browser = browser_map[choice]
    ui_status('success', f'已选择浏览器: {browser.upper()}')
    return browser


def ask_yes_no(prompt):
    answer = input(ui_prompt(f'{prompt} (y/n): ')).strip().lower()
    while answer not in ('y', 'n', 'yes', 'no'):
        answer = input(ui_prompt('请输入 y 或 n: ')).strip().lower()
    return answer in ('y', 'yes')


class BrowserSession:
    def __init__(self, browser_type=None):
        self.browser_type = browser_type or DEFAULT_BROWSER
        self.driver = None

    def _create_service(self, service_cls, driver_path):
        kwargs = {
            'executable_path': driver_path,
            'log_output': os.devnull,
        }
        try:
            return service_cls(**kwargs)
        except TypeError:
            kwargs.pop('log_output', None)
            return service_cls(**kwargs)

    def create_driver(self):
        service_cls, driver_cls, options_cls = SUPPORTED_BROWSERS[self.browser_type]
        options = options_cls()
        options.add_argument(f'--window-size={FIXED_WINDOW_SIZE[0]},{FIXED_WINDOW_SIZE[1]}')
        # 关闭浏览器通知和其他干扰
        options.add_argument('--disable-blink-features=AutomationControlled')
        if self.browser_type in CHROMIUM_BROWSERS:
            options.add_argument('--log-level=3')
            options.add_argument('--disable-logging')
        if hasattr(options, 'add_experimental_option'):
            excluded_switches = ["enable-automation"]
            if self.browser_type in CHROMIUM_BROWSERS:
                excluded_switches.append("enable-logging")
            options.add_experimental_option("excludeSwitches", excluded_switches)
            options.add_experimental_option('useAutomationExtension', False)
        
        driver_name = f'{self.browser_type}Driver.exe'
        if self.browser_type == 'ie':
            driver_name = 'ieDriverServer.exe'
        driver_path = FilePath.resource_path(driver_name)
        if not os.path.exists(driver_path):
            raise FileNotFoundError(f'浏览器驱动未找到: {driver_path}')
        # Selenium 4.x 使用新的 API
        service = self._create_service(service_cls, driver_path)
        try:
            self.driver = driver_cls(service=service, options=options)
            try:
                self.driver.fullscreen_window()
            except Exception:
                pass
        except SessionNotCreatedException as e:
            msg = str(e)
            if 'only supports' in msg or 'Current browser version is' in msg:
                raise RuntimeError(
                    f'浏览器驱动与浏览器版本不匹配：\n{msg}\n'
                    f'请下载与当前 {self.browser_type} 浏览器版本匹配的驱动，或者切换到其他浏览器驱动后重试。'
                ) from e
            raise
        except WebDriverException as e:
            raise RuntimeError(f'浏览器启动失败: {e}') from e

    def get_cookie_string(self):
        cookies = self.driver.get_cookies()
        return '; '.join(f"{cookie['name']}={cookie['value']}" for cookie in cookies) + ';'

    def prompt_settings(self):
        self.browser_type = choose_browser()
        ui_status('info', '手动登录模式：浏览器窗口将最大化，请在浏览器中输入账号密码并完成验证。')

    def wait(self, locator, timeout=6):
        return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(locator))

    def check_login_success(self):
        """检查是否登录成功，通过 URL、已登录元素和 cookie 判断。"""
        try:
            current_url = self.driver.current_url.lower()
            if 'chaoxing' not in current_url:
                return False
            if any(token in current_url for token in ('login', 'passport', 'verify', 'cas', 'redirect')):
                return False

            known_locators = [
                (By.CLASS_NAME, 'personalInfo'),
                (By.XPATH, "//*[contains(text(), '退出')]"),
                (By.XPATH, "//*[contains(text(), '退出登录')]"),
                (By.XPATH, "//*[contains(text(), '我的课程')]"),
                (By.XPATH, "//*[contains(text(), '课程中心')]")
            ]
            for locator in known_locators:
                try:
                    if self.driver.find_element(*locator):
                        return True
                except NoSuchElementException:
                    continue

            cookie_names = {cookie['name'] for cookie in self.driver.get_cookies()}
            if cookie_names & {'UID', 'JSESSIONID', 'JSESSIONIDSSO', 'SESSIONID', 'SESSDATA'}:
                return True
            return False
        except Exception:
            return False

    def wait_for_manual_login(self):
        ui_status('info', '请在浏览器中完成登录，并完成滑块验证。')
        ui_status('info', '完成后切换回此窗口并按回车继续。')
        while True:
            input(ui_prompt('按回车继续...'))
            if self.check_login_success():
                ui_status('success', '检测到已登录状态。')
                return True
            ui_status('warn', '未检测到成功登录，请确认浏览器中的登录状态。')
            if not ask_yes_no('是否继续等待登录？'):
                return False

    def signin(self):
        """执行登录流程并返回 cookie"""
        ui_title('自动登录流程')

        self.prompt_settings()

        try:
            ui_status('progress', '正在创建浏览器驱动...')
            self.create_driver()
            ui_status('success', '浏览器已启动。')
        except FileNotFoundError as e:
            ui_status('error', f'错误: {e}')
            raise
        except Exception as e:
            ui_status('error', f'浏览器启动失败: {e}')
            raise

        try:
            ui_status('progress', '正在打开登录页面...')
            self.driver.get('https://v8.chaoxing.com')
            self.driver.maximize_window()  # 确保浏览器窗口最大化
            time.sleep(1)
            success = self.wait_for_manual_login()

            if not success:
                raise RuntimeError('登录失败，请检查浏览器中的登录状态。')

            cookie_string = self.get_cookie_string()
            ui_status('success', f'Cookie 获取成功，长度: {len(cookie_string)}')
            return cookie_string
        except Exception as e:
            ui_status('error', f'登录过程中出错: {e}')
            raise
        finally:
            ui_status('info', '正在关闭浏览器...')
            try:
                self.driver.quit()
                ui_status('success', '浏览器已关闭。')
            except:
                pass


def load_api_key():
    env_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if env_key:
        return env_key
    key = api_store.read()
    if key:
        return key
    return api_store.get_or_prompt()


def _is_context_too_long_error(error):
    message = str(error).lower()
    keywords = (
        'context length',
        'maximum context',
        'max tokens',
        'too many tokens',
        'tokens',
        'input is too long',
        'context window',
    )
    return any(keyword in message for keyword in keywords)


def _should_exit_qa(user_input):
    return user_input.strip().lower() in QA_EXIT_COMMANDS


def _truncate_qa_history_if_needed(qa_messages):
    if QA_HISTORY_LIMIT is None:
        return qa_messages
    max_messages = QA_HISTORY_LIMIT * 2
    if len(qa_messages) <= max_messages:
        return qa_messages
    return qa_messages[-max_messages:]


def open_qa_loop(client, model_name, temperature, base_messages):
    ui_title('开放问答模式')
    ui_status('info', '输入问题即可继续提问，输入 exit/quit/退出/q 返回主菜单。')

    qa_messages = []
    while True:
        user_input = input("\n你: ").strip()
        if not user_input:
            ui_status('warn', '请输入有效问题，或输入 exit/quit/退出/q 返回主菜单。')
            continue
        if _should_exit_qa(user_input):
            ui_status('success', '已退出开放问答模式，返回主菜单。')
            return

        qa_messages.append({'role': 'user', 'content': user_input})
        qa_messages = _truncate_qa_history_if_needed(qa_messages)

        while True:
            messages = base_messages + qa_messages
            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    temperature=temperature,
                    messages=messages,
                    stream=False,
                )
                answer_text = completion.choices[0].message.content
                print("\nAI:")
                ui_block(answer_text)
                qa_messages.append({'role': 'assistant', 'content': answer_text})
                qa_messages = _truncate_qa_history_if_needed(qa_messages)
                break
            except Exception as e:
                if _is_context_too_long_error(e):
                    if len(qa_messages) >= 2:
                        qa_messages = qa_messages[2:]
                        continue
                    ui_status('error', '上下文过长，无法在保留全文作业内容的情况下继续回答。')
                    ui_block('请简化问题，或退出开放问答模式。')
                    break
                ui_status('error', f'问答请求失败: {e}')
                break


def _config_menu():
    ui_menu('配置管理', [
        '1. 修改作业地址',
        '2. 修改 Cookie',
        '3. 修改 API 密钥',
        '0. 返回主菜单',
    ])

    choice = input(ui_prompt('请选择 (0-3): ')).strip()
    if choice == '1':
        address_store.update()
    elif choice == '2':
        cookie_store.update()
    elif choice == '3':
        api_store.update()
    elif choice == '0':
        return
    else:
        ui_status('warn', '无效选择，请输入 0-3。')


def build_request_headers(cookie_value):
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
        ),
        'Cookie': cookie_value,
    }


def fetch_homework_page(address, cookie_value):
    response = requests.get(address, headers=build_request_headers(cookie_value), timeout=15)
    response.raise_for_status()
    return response.text


def simplify_text_for_compare(text):
    if text is None:
        return ''
    normalized = html_lib.unescape(str(text))
    normalized = normalized.replace('\xa0', ' ').replace('\u3000', ' ')
    normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
    normalized = re.sub(r'<br\s*/?>', '\n', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<[^>]+>', ' ', normalized)
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    normalized = re.sub(r'\n+', '\n', normalized)
    return normalized.strip()


def clean_question_text(text):
    normalized = simplify_text_for_compare(text)
    if not normalized:
        return ''

    lines = []
    for raw_line in normalized.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        if line in EDITOR_NOISE_TOKENS or line.rstrip(':：') in EDITOR_NOISE_TOKENS:
            continue
        lines.append(line)

    deduplicated = []
    for line in lines:
        if not deduplicated or deduplicated[-1] != line:
            deduplicated.append(line)
    return '\n'.join(deduplicated).strip()


def normalize_type_name(raw_name='', type_value=''):
    raw = clean_question_text(raw_name or '')
    if '单选' in raw:
        return '单选题'
    if '多选' in raw:
        return '多选题'
    if '填空' in raw:
        return '填空题'
    if '判断' in raw:
        return '判断题'
    if '论述' in raw:
        return '论述题'
    if type_value in QUESTION_TYPE_MAP:
        return QUESTION_TYPE_MAP[type_value]
    if type_value in TEXT_QUESTION_TYPE_VALUES:
        return '文本题'
    return '未知题型'


def extract_question_number(question_block, header):
    sources = [question_block.get('aria-label', '')]
    if header is not None:
        sources.append(header.get_text(' ', strip=True))
    for source in sources:
        match = re.search(r'(\d+)\s*\.', source)
        if match:
            return int(match.group(1))
    return None


def extract_question_stem(question_block, question_no, type_name):
    header = question_block.find('h3')
    if header is None:
        return ''

    paragraphs = []
    for paragraph in header.find_all('p'):
        text = clean_question_text(paragraph.get_text('\n', strip=True))
        if text:
            paragraphs.append(text)
    if paragraphs:
        return '\n'.join(paragraphs).strip()

    raw_text = clean_question_text(header.get_text('\n', strip=True))
    filtered_lines = []
    for line in raw_text.split('\n'):
        if question_no is not None and re.fullmatch(rf'{question_no}\.?', line):
            continue
        normalized_line = line.replace('（', '(').replace('）', ')')
        if normalized_line.startswith('(') and type_name != '未知题型' and type_name.rstrip('题') in normalized_line:
            continue
        filtered_lines.append(line)
    return '\n'.join(filtered_lines).strip()


def extract_question_options(question_block, qid):
    options = []
    selector = "div[onclick*='addChoice'], div[onclick*='addMultipleChoice']"
    for option_el in question_block.select(selector):
        span = option_el.select_one(f"span.choice{qid}") or option_el.select_one("span[data]")
        if span is None:
            continue

        code = clean_question_text(span.get_text(' ', strip=True)).upper()
        value = clean_question_text(span.get('data') or code)
        answer_node = option_el.select_one('.answer_p')
        option_text = clean_question_text(
            answer_node.get_text('\n', strip=True) if answer_node else option_el.get_text('\n', strip=True)
        )
        if code:
            option_text = re.sub(rf'^{re.escape(code)}\s*', '', option_text).strip()

        option = {
            'code': code or value.upper(),
            'value': value,
            'text': option_text,
        }
        if option not in options:
            options.append(option)
    return options


def extract_writable_fields(question_block, qid, type_value):
    blank_count = 0
    blank_size_input = question_block.find('input', attrs={'name': f'tiankongsize{qid}'})
    if blank_size_input is not None:
        try:
            blank_count = int(str(blank_size_input.get('value', '0')).strip() or '0')
        except ValueError:
            blank_count = 0

    blank_fields = []
    text_fields = []
    for textarea in question_block.find_all('textarea'):
        textarea_id = (textarea.get('id') or '').strip()
        textarea_name = (textarea.get('name') or '').strip()
        field = {'id': textarea_id, 'name': textarea_name}

        if textarea_id.startswith(f'answerEditor{qid}') or textarea_name.startswith(f'answerEditor{qid}'):
            suffix = textarea_id or textarea_name
            match = re.search(rf'{re.escape(qid)}(\d+)$', suffix)
            field['index'] = int(match.group(1)) if match else len(blank_fields) + 1
            blank_fields.append(field)
        elif textarea_id == f'answer{qid}' or textarea_name == f'answer{qid}':
            text_fields.append(field)
        elif textarea_id or textarea_name:
            text_fields.append(field)

    blank_fields.sort(key=lambda item: item.get('index', 0))
    if type_value == '2' or blank_fields:
        if not blank_count:
            blank_count = len(blank_fields)
        fields = [{'id': item['id'], 'name': item['name']} for item in blank_fields]
        if blank_count and len(fields) < blank_count:
            for index in range(len(fields) + 1, blank_count + 1):
                fields.append({
                    'id': f'answerEditor{qid}{index}',
                    'name': f'answerEditor{qid}{index}',
                })
        return blank_count, fields

    if text_fields:
        return blank_count, text_fields[:1]
    return blank_count, []


def extract_questions_from_page(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    questions = []
    for order, question_block in enumerate(soup.select('div.singleQuesId'), start=1):
        qid = str(question_block.get('data') or '').strip()
        if not qid:
            block_id = str(question_block.get('id') or '')
            match = re.search(r'question(\d+)', block_id)
            qid = match.group(1) if match else ''
        if not qid:
            continue

        type_input = (
            question_block.find('input', id=f'answertype{qid}')
            or question_block.find('input', attrs={'name': f'answertype{qid}'})
        )
        type_value = str(type_input.get('value', '') if type_input else '').strip()

        raw_type_name = question_block.get('typename') or question_block.get('typeName') or ''
        if not raw_type_name:
            type_span = question_block.select_one('h3 .colorShallow')
            raw_type_name = type_span.get_text(' ', strip=True) if type_span else ''

        type_name = normalize_type_name(raw_type_name, type_value)
        question_no = extract_question_number(question_block, question_block.find('h3'))
        stem = extract_question_stem(question_block, question_no, type_name)
        options = extract_question_options(question_block, qid)
        blank_count, input_fields = extract_writable_fields(question_block, qid, type_value)

        if type_name == '未知题型' and input_fields:
            type_name = '文本题'

        questions.append({
            'order': order,
            'qid': qid,
            'question_no': question_no or order,
            'type_value': type_value,
            'type_name': type_name,
            'stem': stem,
            'options': options,
            'blank_count': blank_count,
            'input_fields': input_fields,
            'hidden_answer_field': f'answer{qid}',
            'supports_autofill': type_value in {'0', '1', '2', '3', '6'} or bool(input_fields),
        })
    return questions


def serialize_questions_for_ai(questions):
    payload = []
    for question in questions:
        item = {
            'qid': question['qid'],
            '题号': question['question_no'],
            'type': question['type_name'],
            '题干': question['stem'],
        }
        if question['options']:
            item['选项'] = [
                {'code': option['code'], 'content': option['text']}
                for option in question['options']
            ]
        if question['blank_count']:
            item['填空数量'] = question['blank_count']
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_questions_for_display(questions):
    lines = []
    for question in questions:
        lines.append(f"{question['question_no']}. [{question['type_name']}] qid={question['qid']}")
        lines.append(question['stem'])
        if question['options']:
            for option in question['options']:
                lines.append(f"{option['code']}. {option['text']}")
        elif question['blank_count']:
            lines.append(f"填空数量: {question['blank_count']}")
        lines.append('')
    return '\n'.join(lines).strip()


def build_ai_prompt(questions):
    question_json = serialize_questions_for_ai(questions)
    return (
        "你是超星作业答题助手。请根据题目内容，按题目顺序给出尽可能准确的答案。\n"
        "必须严格遵守以下输出要求：\n"
        "1. 第一部分必须是一个合法 JSON 对象，且只能包含 answers 字段。\n"
        "2. JSON 中的每一项都必须包含 qid、type、answer 三个字段，并覆盖所有题目。\n"
        "3. JSON 后面可以再补充一段中文说明，但 JSON 必须放在最前面。\n"
        "4. 答案格式必须遵守：单选题返回单个选项字母；多选题返回选项字母数组；"
        "填空题返回按空位顺序排列的数组；判断题返回 true 或 false；"
        "论述题/文本题返回完整文本。\n"
        "5. 不要遗漏 qid，不要输出与题目无关的内容。\n\n"
        "输出示例：\n"
        "{\n"
        '  "answers": [\n'
        '    {"qid": "123", "type": "单选题", "answer": "A"},\n'
        '    {"qid": "456", "type": "多选题", "answer": ["A", "C"]},\n'
        '    {"qid": "789", "type": "填空题", "answer": ["答案1", "答案2"]},\n'
        '    {"qid": "101", "type": "判断题", "answer": "true"},\n'
        '    {"qid": "102", "type": "论述题", "answer": "完整作答内容"}\n'
        "  ]\n"
        "}\n\n"
        "以下是结构化题目数据：\n"
        f"{question_json}"
    )


def extract_json_block(text):
    if not text:
        return ''

    for pattern in (r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```'):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate.startswith('{') and candidate.endswith('}'):
                return candidate

    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', text):
        start = match.start()
        try:
            obj, end = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return text[start:start + end]
        except json.JSONDecodeError:
            continue
    return ''


def decode_json_object(text):
    json_text = extract_json_block(text)
    if not json_text:
        raise ValueError('未找到合法的 JSON 答案块。')
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'JSON 解析失败: {exc}') from exc


def repair_ai_answer_json(result, questions, client, model_name, temperature=0.0):
    question_specs = []
    for question in questions:
        spec = {
            'qid': question['qid'],
            'type': question['type_name'],
        }
        if question['options']:
            spec['valid_options'] = [option['code'] for option in question['options']]
        if question['blank_count']:
            spec['blank_count'] = question['blank_count']
        question_specs.append(spec)

    repair_prompt = (
        "请把下面这段作业答案整理成一个严格合法的 JSON 对象，并且只能输出 JSON，不要输出解释。\n"
        "JSON 格式必须为：\n"
        "{\n"
        '  "answers": [\n'
        '    {"qid": "...", "type": "...", "answer": "..."}\n'
        "  ]\n"
        "}\n"
        "题目约束如下：\n"
        f"{json.dumps(question_specs, ensure_ascii=False, indent=2)}\n\n"
        "原始答案如下：\n"
        f"{result}"
    )

    completion = client.chat.completions.create(
        model=model_name,
        temperature=temperature,
        messages=[{'role': 'user', 'content': repair_prompt}],
        stream=False,
    )
    return completion.choices[0].message.content or ''


def normalize_lookup_key(value):
    if value is None:
        return ''
    text = html_lib.unescape(str(value)).strip().lower()
    text = text.replace('\xa0', ' ').replace('\u3000', ' ')
    text = re.sub(r'^(答案|选项|option)', '', text)
    text = re.sub(r'[\s`"\'“”‘’<>《》【】\[\]（）()：:，,。．、;；|]+', '', text)
    return text


def build_option_lookup(question):
    lookup = {}
    for option in question['options']:
        for key in {
            normalize_lookup_key(option.get('code')),
            normalize_lookup_key(option.get('value')),
            normalize_lookup_key(option.get('text')),
        }:
            if key and key not in lookup:
                lookup[key] = option
    return lookup


def normalize_choice_answer(question, raw_answer):
    if isinstance(raw_answer, list):
        if len(raw_answer) != 1:
            raise ValueError('单选题必须返回单个答案。')
        raw_answer = raw_answer[0]

    lookup = build_option_lookup(question)
    valid_codes = {option['code'] for option in question['options']}
    token = normalize_lookup_key(raw_answer)

    if token in lookup:
        return lookup[token]['code']

    raw_text = str(raw_answer or '').strip()
    letter_match = re.search(r'[A-Za-z]', raw_text)
    if letter_match:
        code = letter_match.group(0).upper()
        if code in valid_codes:
            return code

    raise ValueError('单选题答案不在页面可选范围内。')


def normalize_judgment_answer(question, raw_answer):
    if isinstance(raw_answer, list):
        if len(raw_answer) != 1:
            raise ValueError('判断题必须返回单个答案。')
        raw_answer = raw_answer[0]

    lookup = build_option_lookup(question)
    token = normalize_lookup_key(raw_answer)
    if token in lookup:
        return str(lookup[token]['value']).lower()

    truthy = {'a', 'true', '对', '正确', '是', 'yes', '√', '1', 't'}
    falsy = {'b', 'false', '错', '错误', '否', 'no', '×', '0', 'f'}
    if token in truthy:
        target = 'true'
    elif token in falsy:
        target = 'false'
    else:
        raw_text = str(raw_answer or '').strip()
        ab_match = re.search(r'[ABab]', raw_text)
        if not ab_match:
            raise ValueError('判断题答案不合法。')
        target = 'true' if ab_match.group(0).upper() == 'A' else 'false'

    valid_values = {str(option['value']).lower() for option in question['options']}
    if valid_values and target not in valid_values:
        raise ValueError('判断题答案不在页面可选范围内。')
    return target


def normalize_multiple_answer(question, raw_answer):
    lookup = build_option_lookup(question)
    valid_codes = {option['code'] for option in question['options']}

    if isinstance(raw_answer, list):
        tokens = raw_answer
    else:
        raw_text = html_lib.unescape(str(raw_answer or '')).strip()
        if not raw_text:
            raise ValueError('多选题答案不能为空。')
        compact = re.sub(r'[\s、，,;/；|]+', '', raw_text)
        if len(compact) > 1 and all(char.upper() in valid_codes for char in compact):
            tokens = list(compact)
        else:
            tokens = [token for token in re.split(r'[\s、，,;/；|]+', raw_text) if token]

    selected_codes = []
    for token in tokens:
        normalized_key = normalize_lookup_key(token)
        if normalized_key in lookup:
            code = lookup[normalized_key]['code']
        else:
            raw_text = str(token or '').strip()
            letter_match = re.search(r'[A-Za-z]', raw_text)
            code = letter_match.group(0).upper() if letter_match else ''
            if code not in valid_codes:
                raise ValueError('多选题包含无效选项。')
        if code not in selected_codes:
            selected_codes.append(code)

    if not selected_codes:
        raise ValueError('多选题至少需要一个有效选项。')

    ordered_codes = [option['code'] for option in question['options'] if option['code'] in selected_codes]
    if len(ordered_codes) != len(selected_codes):
        raise ValueError('多选题包含超出页面范围的选项。')
    return ordered_codes


def normalize_blank_answer(question, raw_answer):
    blank_count = question['blank_count']
    if blank_count <= 0:
        raise ValueError('未识别到填空数量。')

    if isinstance(raw_answer, list):
        values = raw_answer
    elif blank_count == 1:
        values = [raw_answer]
    else:
        raise ValueError(f'填空题需要返回 {blank_count} 个答案。')

    cleaned_values = [clean_question_text(value if value is not None else '') for value in values]
    if len(cleaned_values) != blank_count:
        raise ValueError(f'填空数量不匹配，期望 {blank_count} 个答案。')
    if any(not value for value in cleaned_values):
        raise ValueError('填空题存在空答案。')
    return cleaned_values


def normalize_text_answer(question, raw_answer):
    if isinstance(raw_answer, list):
        text = '\n'.join(str(part).strip() for part in raw_answer if str(part).strip())
    else:
        text = str(raw_answer or '').strip()
    cleaned = clean_question_text(text)
    if not cleaned:
        raise ValueError(f"{question['type_name']}答案不能为空。")
    return cleaned


def validate_structured_answers(answer_payload, questions):
    if isinstance(answer_payload, list):
        answers = answer_payload
    elif isinstance(answer_payload, dict):
        answers = answer_payload.get('answers')
    else:
        raise ValueError('答案 JSON 顶层必须是对象或数组。')

    if not isinstance(answers, list) or not answers:
        raise ValueError('答案 JSON 中缺少 answers 数组。')

    question_map = {question['qid']: question for question in questions}
    normalized_answers = []
    seen_qids = set()
    errors = []

    for item in answers:
        if not isinstance(item, dict):
            errors.append('answers 数组中存在非对象项。')
            continue

        qid = str(item.get('qid', '')).strip()
        if not qid or qid not in question_map:
            errors.append(f'存在无效 qid: {qid or "空值"}。')
            continue
        if qid in seen_qids:
            errors.append(f'qid={qid} 重复出现。')
            continue

        question = question_map[qid]
        seen_qids.add(qid)

        provided_type = normalize_type_name(item.get('type', ''), question['type_value'])
        expected_type = question['type_name']
        if item.get('type') and provided_type != expected_type:
            if not (expected_type == '文本题' and provided_type in {'文本题', '论述题'}):
                errors.append(
                    f"第 {question['question_no']} 题类型不匹配，页面类型为 {expected_type}，返回类型为 {provided_type}。"
                )
                continue

        raw_answer = item.get('answer')
        try:
            if question['type_value'] == '0':
                normalized_answer = normalize_choice_answer(question, raw_answer)
            elif question['type_value'] == '1':
                normalized_answer = normalize_multiple_answer(question, raw_answer)
            elif question['type_value'] == '2':
                normalized_answer = normalize_blank_answer(question, raw_answer)
            elif question['type_value'] == '3':
                normalized_answer = normalize_judgment_answer(question, raw_answer)
            else:
                normalized_answer = normalize_text_answer(question, raw_answer)
        except ValueError as exc:
            errors.append(f"第 {question['question_no']} 题校验失败: {exc}")
            continue

        normalized_answers.append({
            'qid': qid,
            'question_no': question['question_no'],
            'type': expected_type,
            'type_value': question['type_value'],
            'answer': normalized_answer,
        })

    missing_questions = [question for question in questions if question['qid'] not in seen_qids]
    if missing_questions:
        errors.append(
            '缺少题目答案: ' + '、'.join(
                f"{question['question_no']}(qid={question['qid']})"
                for question in missing_questions
            )
        )

    if errors:
        raise ValueError('；'.join(errors))

    normalized_answers.sort(key=lambda item: question_map[item['qid']]['order'])
    return {'answers': normalized_answers}


def parse_ai_answer(result, questions, client=None, model_name=None, temperature=0.0):
    attempts = [result]
    repaired_result = None
    last_error = None

    for index in range(2):
        if index == 1:
            if client is None or model_name is None:
                break
            repaired_result = repair_ai_answer_json(result, questions, client, model_name, temperature)
            attempts.append(repaired_result)

        candidate = attempts[index]
        try:
            payload = decode_json_object(candidate)
            structured_answer = validate_structured_answers(payload, questions)
            structured_answer['json_text'] = json.dumps(
                {'answers': structured_answer['answers']},
                ensure_ascii=False,
                indent=2,
            )
            if repaired_result:
                structured_answer['repaired_json'] = repaired_result
            return structured_answer
        except Exception as exc:
            last_error = exc

    raise ValueError(f'AI 答案解析失败: {last_error}') from last_error


def parse_cookie_string(cookie_string):
    cookies = []
    for item in str(cookie_string or '').split(';'):
        piece = item.strip()
        if not piece or '=' not in piece:
            continue
        name, value = piece.split('=', 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies.append({'name': name, 'value': value})
    return cookies


def wait_for_page_ready(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script('return document.readyState') == 'complete'
    )


def wait_for_editor_ready(driver, textarea_id, timeout=10):
    WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script(
            """
            const textareaId = arguments[0];
            const textarea = document.getElementById(textareaId);
            if (!textarea) {
                return false;
            }
            if (!window.UE || typeof UE.getEditor !== 'function') {
                return true;
            }
            try {
                const editor = UE.getEditor(textareaId);
                return !editor || !!editor.isReady;
            } catch (error) {
                return true;
            }
            """,
            textarea_id,
        )
    )


def inject_cookies_and_open(driver, address, cookie_string):
    parsed_address = urlparse(address)
    if not parsed_address.scheme or not parsed_address.netloc:
        raise ValueError('作业地址格式无效，请检查 page_address.txt。')

    cookies = parse_cookie_string(cookie_string)
    if not cookies:
        raise ValueError('Cookie 为空或格式无效，请重新登录获取 Cookie。')

    base_url = f'{parsed_address.scheme}://{parsed_address.netloc}'
    driver.get(base_url)
    wait_for_page_ready(driver)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            continue

    driver.get(address)
    wait_for_page_ready(driver)


def get_hidden_answer_value(driver, qid):
    return driver.execute_script(
        "var el = document.getElementById(arguments[0]); return el ? (el.value || '') : '';",
        f'answer{qid}',
    )


def click_option_element(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.2)
    try:
        element.click()
    except Exception:
        driver.execute_script('arguments[0].click();', element)
    time.sleep(0.2)


def set_editor_value(driver, textarea_id, value, question_id, question_type):
    return driver.execute_script(
        """
        const textareaId = arguments[0];
        const value = arguments[1] == null ? '' : String(arguments[1]);
        const questionId = arguments[2];
        const questionType = arguments[3];
        const textarea = document.getElementById(textareaId);
        if (!textarea) {
            return { ok: false, reason: 'textarea_not_found', textareaId };
        }

        const escapeHtml = (input) => input.replace(/[&<>"]/g, (char) => (
            {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[char]
        ));
        const buildHtml = (text) => {
            const lines = text.replace(/\\r\\n/g, '\\n').replace(/\\r/g, '\\n').split('\\n');
            return lines.map((line) => `<p>${line ? escapeHtml(line) : '<br/>'}</p>`).join('');
        };

        let editor = null;
        try {
            if (window.UE && typeof UE.getEditor === 'function') {
                editor = UE.getEditor(textareaId);
            }
        } catch (error) {}

        try {
            if (editor && typeof editor.setContent === 'function' && editor.isReady !== false) {
                editor.setContent(buildHtml(value));
                if (typeof editor.sync === 'function') {
                    editor.sync();
                }
            } else {
                textarea.value = value;
            }
        } catch (error) {
            textarea.value = value;
        }

        if (!textarea.value && value) {
            textarea.value = value;
        }

        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));

        if (typeof syncAnswer === 'function') {
            try {
                syncAnswer(String(questionId), String(questionType));
            } catch (error) {}
        }
        if (typeof loadEditorAnswerd === 'function') {
            try {
                loadEditorAnswerd(String(questionId), questionType);
            } catch (error) {}
        }
        if (typeof answerContentChange === 'function') {
            try {
                answerContentChange();
            } catch (error) {}
        }

        let plainText = '';
        let htmlContent = textarea.value || '';
        try {
            if (editor && typeof editor.getContentTxt === 'function') {
                plainText = editor.getContentTxt();
            }
            if (editor && typeof editor.getContent === 'function') {
                htmlContent = editor.getContent();
            }
            if (editor && typeof editor.sync === 'function') {
                editor.sync();
            }
        } catch (error) {}

        return {
            ok: true,
            textareaId,
            textareaValue: textarea.value || '',
            plainText,
            htmlContent,
        };
        """,
        textarea_id,
        value,
        str(question_id),
        str(question_type or ''),
    )


def read_text_editor_state(driver, textarea_id, qid, question_type='6'):
    return driver.execute_script(
        """
        const textareaId = arguments[0];
        const questionId = arguments[1];
        const questionType = arguments[2];
        const textarea = document.getElementById(textareaId);
        const answerSheet = questionId ? document.getElementById('answerSheet' + questionId) : null;
        if (!textarea) {
            return { ok: false, reason: 'textarea_not_found', textareaId };
        }

        let editor = null;
        try {
            if (window.UE && typeof UE.getEditor === 'function') {
                editor = UE.getEditor(textareaId);
            }
        } catch (error) {}

        try {
            if (editor && typeof editor.sync === 'function') {
                editor.sync();
            }
        } catch (error) {}

        if (typeof syncAnswer === 'function') {
            try {
                syncAnswer(String(questionId), String(questionType));
            } catch (error) {}
        }
        if (typeof loadEditorAnswerd === 'function') {
            try {
                loadEditorAnswerd(String(questionId), questionType);
            } catch (error) {}
        }

        let plainText = '';
        let htmlContent = '';
        let textareaValue = textarea.value || '';
        try {
            if (editor && typeof editor.getContentTxt === 'function') {
                plainText = editor.getContentTxt() || '';
            }
            if (editor && typeof editor.getContent === 'function') {
                htmlContent = editor.getContent() || '';
            }
            if (editor && typeof editor.sync === 'function') {
                editor.sync();
                textareaValue = textarea.value || textareaValue;
            }
        } catch (error) {}

        return {
            ok: true,
            textareaId,
            textareaValue,
            plainText,
            htmlContent,
            answerSheetActive: !!(answerSheet && answerSheet.classList.contains('active')),
        };
        """,
        textarea_id,
        str(qid or ''),
        str(question_type or ''),
    )


def text_answer_matches(expected_text, state):
    expected = simplify_text_for_compare(expected_text)
    if not expected:
        return True

    for key in ('plainText', 'textareaValue', 'htmlContent'):
        actual = simplify_text_for_compare(state.get(key))
        if actual and (expected in actual or actual in expected):
            return True

    html_content = simplify_text_for_compare(state.get('htmlContent'))
    if html_content and state.get('answerSheetActive'):
        return True
    return False


def wait_for_text_answer_sync(driver, textarea_id, qid, expected_text, question_type='6', timeout=TEXT_VERIFY_TIMEOUT):
    deadline = time.time() + timeout
    latest_state = {}
    while True:
        latest_state = read_text_editor_state(driver, textarea_id, qid, question_type)
        if latest_state.get('ok') and text_answer_matches(expected_text, latest_state):
            return latest_state
        if time.time() >= deadline:
            return latest_state
        time.sleep(TEXT_VERIFY_INTERVAL)


def fill_choice_question(driver, qid, expected_answer):
    question_el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f'#question{qid}'))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    option_elements = question_el.find_elements(By.CSS_SELECTOR, "div[onclick*='addChoice']")
    if not option_elements:
        raise RuntimeError('未找到可点击的单选/判断选项。')

    target_element = None
    expected_hidden_value = None
    for option_element in option_elements:
        data_value = driver.execute_script(
            "var span = arguments[0].querySelector('span[data]'); return span ? (span.getAttribute('data') || '') : '';",
            option_element,
        ) or ''
        code = driver.execute_script(
            "var span = arguments[0].querySelector('span[data]'); return span ? (span.textContent || '') : '';",
            option_element,
        ).strip().upper()
        if expected_answer.lower() == data_value.lower() or expected_answer.upper() == code:
            target_element = option_element
            expected_hidden_value = data_value or code
            break

    if target_element is None or expected_hidden_value is None:
        raise RuntimeError(f'页面中未找到答案 {expected_answer} 对应的选项。')

    current_value = get_hidden_answer_value(driver, qid)
    if current_value == expected_hidden_value:
        return expected_hidden_value

    click_option_element(driver, target_element)
    updated_value = get_hidden_answer_value(driver, qid)
    if updated_value != expected_hidden_value:
        raise RuntimeError(f'点击后隐藏答案未同步，期望 {expected_hidden_value}，实际 {updated_value!r}。')
    return updated_value


def fill_multiple_question(driver, qid, expected_answers):
    question_el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f'#question{qid}'))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    option_elements = question_el.find_elements(By.CSS_SELECTOR, "div[onclick*='addMultipleChoice']")
    if not option_elements:
        raise RuntimeError('未找到可点击的多选选项。')

    target_set = {str(answer).upper() for answer in expected_answers}
    option_rows = []
    available_codes = set()
    for option_element in option_elements:
        code = driver.execute_script(
            "var span = arguments[0].querySelector('span[data]'); return span ? (span.getAttribute('data') || '') : '';",
            option_element,
        ).strip().upper()
        selected = driver.execute_script(
            """
            const option = arguments[0];
            const marker = option.querySelector('.num_option_dx');
            if (marker && marker.classList.contains('check_answer_dx')) {
                return true;
            }
            return option.getAttribute('aria-checked') === 'true';
            """,
            option_element,
        )
        option_rows.append({'code': code, 'element': option_element, 'selected': selected})
        if code:
            available_codes.add(code)

    invalid_codes = target_set - available_codes
    if invalid_codes:
        raise RuntimeError(f'页面缺少选项: {",".join(sorted(invalid_codes))}')

    for row in option_rows:
        should_select = row['code'] in target_set
        if should_select != bool(row['selected']):
            click_option_element(driver, row['element'])

    updated_value = get_hidden_answer_value(driver, qid)
    if {char.upper() for char in updated_value} != target_set:
        raise RuntimeError(f'多选隐藏答案校验失败，实际值为 {updated_value!r}。')
    return updated_value


def fill_blank_question(driver, qid, answers):
    question_el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f'#question{qid}'))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    for index, value in enumerate(answers, start=1):
        textarea_id = f'answerEditor{qid}{index}'
        wait_for_editor_ready(driver, textarea_id, timeout=12)
        result = set_editor_value(driver, textarea_id, value, qid, '2')
        if not result.get('ok'):
            raise RuntimeError(f'填空控件 {textarea_id} 写入失败。')

        expected = simplify_text_for_compare(value)
        actual = simplify_text_for_compare(result.get('plainText') or result.get('textareaValue'))
        if expected and expected not in actual and actual not in expected:
            raise RuntimeError(f'填空控件 {textarea_id} 回写校验失败。')
    return True


def fill_text_question(driver, qid, text, type_value='6'):
    question_el = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f'#question{qid}'))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    textarea_id = f'answer{qid}'
    wait_for_editor_ready(driver, textarea_id, timeout=12)
    result = set_editor_value(driver, textarea_id, text, qid, type_value or '6')
    if not result.get('ok'):
        raise RuntimeError(f'文本控件 {textarea_id} 写入失败。')

    state = wait_for_text_answer_sync(driver, textarea_id, qid, text, type_value or '6')
    if text_answer_matches(text, state):
        return state

    diagnostics = (
        f"plain={bool(simplify_text_for_compare(state.get('plainText')))}, "
        f"textarea={bool(simplify_text_for_compare(state.get('textareaValue')))}, "
        f"html={bool(simplify_text_for_compare(state.get('htmlContent')))}, "
        f"sheet_active={bool(state.get('answerSheetActive'))}"
    )
    raise RuntimeError(f'文本控件 {textarea_id} 回写校验失败。{diagnostics}')


def autofill_homework(address, cookie, structured_answer, browser_type):
    report = {'success': [], 'failure': [], 'skipped': []}

    session = BrowserSession(browser_type)
    session.create_driver()
    driver = session.driver

    ui_status('progress', '正在打开作业页并注入 Cookie...')
    inject_cookies_and_open(driver, address, cookie)

    current_url = driver.current_url.lower()
    if any(token in current_url for token in ('login', 'passport', 'cas', 'verify')):
        raise RuntimeError('页面仍然跳转到登录页，Cookie 可能已失效。')

    for item in structured_answer.get('answers', []):
        qid = item['qid']
        question_no = item.get('question_no')
        type_value = item.get('type_value', '')
        try:
            if type_value == '0':
                fill_choice_question(driver, qid, item['answer'])
            elif type_value == '1':
                fill_multiple_question(driver, qid, item['answer'])
            elif type_value == '2':
                fill_blank_question(driver, qid, item['answer'])
            elif type_value == '3':
                fill_choice_question(driver, qid, item['answer'])
            elif type_value in TEXT_QUESTION_TYPE_VALUES or item.get('type') in {'论述题', '文本题'}:
                fill_text_question(driver, qid, item['answer'], type_value or '6')
            else:
                report['skipped'].append({
                    'qid': qid,
                    'question_no': question_no,
                    'reason': f'暂不支持的题型: {item.get("type") or type_value}',
                })
                continue

            report['success'].append({'qid': qid, 'question_no': question_no})
        except Exception as exc:
            report['failure'].append({
                'qid': qid,
                'question_no': question_no,
                'reason': str(exc),
            })

    report['browser_kept_open'] = True
    return report


def print_autofill_report(report):
    success_count = len(report.get('success', []))
    failure_count = len(report.get('failure', []))
    skipped_count = len(report.get('skipped', []))
    failed_numbers = [str(item.get('question_no') or item.get('qid')) for item in report.get('failure', [])]

    notes = [f"失败题号: {', '.join(failed_numbers)}" if failed_numbers else '失败题号: 无']
    ui_summary('自动填写结果', [
        ('成功题数', success_count),
        ('失败题数', failure_count),
        ('跳过题数', skipped_count),
    ], notes=notes)
    ui_status('info', '浏览器已保留在作业页，程序不会自动提交，请先人工检查后再决定是否提交。')


def answer():
    """获取作业内容并使用 AI 解答"""
    ui_title('作业解答助手')

    cookie_value = cookie_store.get_or_prompt()
    address_value = address_store.get_or_prompt().lstrip('\ufeff').strip()

    ui_status('progress', '正在获取作业页面...')
    try:
        page_html = fetch_homework_page(address_value, cookie_value)
    except requests.exceptions.RequestException as e:
        ui_status('error', f'网络请求失败: {e}')
        return ''

    questions = extract_questions_from_page(page_html)
    if not questions:
        ui_status('error', '未找到结构化题目，请检查页面地址、Cookie，或确认页面确实是作业答题页。')
        return ''

    question_overview = format_questions_for_display(questions)
    type_summary = '、'.join(sorted({question['type_name'] for question in questions}))
    ui_summary('题目提取结果', [
        ('题目数量', len(questions)),
        ('题型覆盖', type_summary),
    ])

    mode_choice = ''
    while mode_choice not in ('1', '2'):
        mode_choice = input(ui_prompt('请选择 AI 模式 (1=标准/2=深度思考): ')).strip()

    temperature = 0.0
    model_map = {'1': 'deepseek-chat', '2': 'deepseek-reasoner'}
    model_name = model_map[mode_choice]
    prompt = build_ai_prompt(questions)
    api_key = load_api_key()

    ui_status('info', f'使用模型: {model_name} | 温度: {temperature}')
    ui_status('progress', '正在生成答案...')

    try:
        os.environ['OPENAI_API_KEY'] = api_key
        client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')

        completion = client.chat.completions.create(
            model=model_name,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
            stream=False,
        )

        result = completion.choices[0].message.content
        ui_section('AI 解答结果')
        ui_block(result)

        structured_answer = None
        try:
            structured_answer = parse_ai_answer(
                result,
                questions,
                client=client,
                model_name=model_name,
                temperature=0.0,
            )
            ui_status('success', f"已解析结构化答案，共 {len(structured_answer['answers'])} 题。")
        except Exception as parse_error:
            ui_status('warn', f'结构化答案解析失败，暂时无法自动填写: {parse_error}')

        if structured_answer and ask_yes_no('是否自动填写到网页'):
            browser_type = choose_browser()
            try:
                report = autofill_homework(address_value, cookie_value, structured_answer, browser_type)
                print_autofill_report(report)
            except Exception as autofill_error:
                ui_status('error', f'自动填写失败: {autofill_error}')

        base_messages = [
            {'role': 'user', 'content': f'作业题目结构如下：\n{question_overview}'},
            {'role': 'assistant', 'content': result},
        ]
        open_qa_loop(client, model_name, temperature, base_messages)
        return result

    except Exception as e:
        ui_status('error', f'API 请求失败: {e}')
        return ''
    finally:
        os.environ.pop('OPENAI_API_KEY', None)


def main():
    ui_title('超星学习通自动作业助手 v2.0', icon='🤖')

    print_browser_driver_status()
    while True:
        ui_menu('主菜单', [
            '1. 自动获取 Cookie 并登录',
            '2. 开始作业解答',
            '3. 修改配置 (地址/Cookie/API)',
            '4. 重新检测浏览器驱动',
            '0. 退出程序',
        ])

        choice = input(ui_prompt('请选择 (0-4): ')).strip()
        if choice == '1':
            try:
                session = BrowserSession()
                cookie_value = session.signin()
                cookie_store.write(cookie_value)
                ui_status('success', f'Cookie 已保存: {cookie_value[:50]}...')
            except Exception as e:
                ui_status('error', f'登录失败: {e}')
        elif choice == '2':
            try:
                answer()
            except KeyboardInterrupt:
                ui_status('warn', '用户中断程序。')
            except Exception as e:
                ui_status('error', f'程序出错: {e}')
        elif choice == '3':
            _config_menu()
        elif choice == '4':
            print_browser_driver_status()
        elif choice == '0':
            break
        else:
            ui_status('warn', '无效选择，请输入 0-4。')

    ui_title('程序已完成')


if __name__ == '__main__':
    main()
