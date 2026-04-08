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
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, SessionNotCreatedException, UnexpectedAlertPresentException

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
import html as html_lib
import json
import time
import os
import re
import sys
import threading
import unicodedata
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from urllib.parse import parse_qs, quote, urljoin, urlparse

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
DEFAULT_PARALLEL_LIMIT = 3
DEFAULT_PARALLEL_RETRIES = 2
DEFAULT_CHAPTER_VIDEO_PLAYBACK_RATE = 2.0
DEFAULT_VIDEO_WAIT_SECONDS = 4 * 60 * 60
VIDEO_STATUS_POLL_INTERVAL = 3.0
PAGE_READY_TIMEOUT = 20
FRAME_READY_TIMEOUT = 20
PERSONAL_SPACE_URL = 'https://i.chaoxing.com/base'
PERSONAL_SPACE_IFRAME_ID = 'frame_content'
COURSE_CARD_IFRAME_PREFIX = 'frame_content'
CHAPTER_IFRAME_ID = 'iframe'
COURSE_TASK_TYPES = ('chapter', 'homework', 'exam')
FOCUS_SENSITIVE_TASK_TYPES = {'chapter'}
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
BROWSER_CHOICE_MAP = {'1': 'edge', '2': 'chrome', '3': 'firefox', '4': 'ie'}
BROWSER_LABELS = {
    'edge': 'Edge (推荐)',
    'chrome': 'Chrome',
    'firefox': 'Firefox',
    'ie': 'IE',
}
AI_MODE_MODEL_MAP = {'1': 'deepseek-chat', '2': 'deepseek-reasoner'}
AI_MODE_LABELS = {'1': '标准模式', '2': '深度思考'}
AI_MODE_ALIASES = {
    '1': '1',
    'standard': '1',
    'chat': '1',
    'deepseek-chat': '1',
    '2': '2',
    'deep': '2',
    'reasoner': '2',
    'deepseek-reasoner': '2',
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


@dataclass
class CourseItem:
    course_name: str
    course_url: str
    courseid: str
    clazzid: str
    cpi: str
    progress_text: str = ''
    status_text: str = ''

    def to_dict(self):
        return asdict(self)


@dataclass
class TaskTarget:
    task_id: str
    task_type: str
    course_name: str
    title: str
    address: str
    course_url: str
    courseid: str
    clazzid: str
    cpi: str
    enc: str = ''
    openc: str = ''
    knowledge_id: str = ''
    pending_count: int = 0
    status_text: str = ''
    submit_policy: str = 'manual'

    def to_dict(self):
        return asdict(self)


@dataclass
class TaskRunResult:
    task_id: str
    task_type: str
    course_name: str
    title: str
    status: str
    retries: int
    kept_open: bool = False
    detail: str = ''
    address: str = ''
    browser_type: str = ''
    answer_count: int = 0
    raw_result: str = ''

    def to_dict(self):
        return asdict(self)


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


def emit_status(notify, level, message):
    handler = notify if callable(notify) else ui_status
    handler(level, message)


def normalize_browser_type(browser_type):
    value = str(browser_type or '').strip().lower()
    if value in SUPPORTED_BROWSERS:
        return value
    if value in BROWSER_CHOICE_MAP:
        return BROWSER_CHOICE_MAP[value]
    raise ValueError(f'不支持的浏览器类型: {browser_type}')


def normalize_ai_mode(ai_mode):
    value = str(ai_mode or '').strip().lower()
    normalized = AI_MODE_ALIASES.get(value)
    if not normalized:
        raise ValueError('AI 模式仅支持 1/2、standard/deep 或对应模型名称。')
    return normalized


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


def get_driver_status(custom_path=None):
    if custom_path is not None:
        normalized = str(custom_path or '').strip()
        FilePath.custom_driver_path = normalized or None

    available, missing = get_available_browsers()
    return {
        'available': available,
        'missing': missing,
        'custom_path': FilePath.custom_driver_path or '',
        'driver_files': dict(DRIVER_FILES),
        'has_available': bool(available),
    }


def load_config_values():
    return {
        'address': address_store.read(),
        'cookie': cookie_store.read(),
        'api_key': api_store.read(),
    }


def save_config_values(address=None, cookie=None, api_key=None):
    if address is not None:
        address_store.write(address)
    if cookie is not None:
        cookie_store.write(cookie)
    if api_key is not None:
        api_store.write(api_key)
    return load_config_values()


def choose_browser():
    ui_menu('选择浏览器类型', [
        '1. Edge (推荐)',
        '2. Chrome',
        '3. Firefox',
        '4. IE',
    ])

    choice = input(ui_prompt('请输入选择 (1-4): ')).strip()

    while choice not in BROWSER_CHOICE_MAP:
        choice = input(ui_prompt('无效选择，请输入 1-4: ')).strip()

    browser = BROWSER_CHOICE_MAP[choice]
    ui_status('success', f'已选择浏览器: {browser.upper()}')
    return browser


def ask_yes_no(prompt):
    answer = input(ui_prompt(f'{prompt} (y/n): ')).strip().lower()
    while answer not in ('y', 'n', 'yes', 'no'):
        answer = input(ui_prompt('请输入 y 或 n: ')).strip().lower()
    return answer in ('y', 'yes')


class LoginWaitController:
    def __init__(self):
        self._check_event = threading.Event()
        self._cancel_event = threading.Event()

    def request_check(self):
        self._check_event.set()

    def cancel(self):
        self._cancel_event.set()
        self._check_event.set()

    def wait_for_action(self, timeout=0.25):
        if self._cancel_event.is_set():
            return 'cancel'
        if self._check_event.wait(timeout):
            self._check_event.clear()
            if self._cancel_event.is_set():
                return 'cancel'
            return 'check'
        return None

    def is_cancelled(self):
        return self._cancel_event.is_set()


class ParallelStopRequested(RuntimeError):
    pass


class ManualReviewRequired(RuntimeError):
    pass


class ParallelRunController:
    def __init__(self):
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._sessions = {}

    def stop_requested(self):
        return self._stop_event.is_set()

    def register_session(self, session):
        if session is None:
            return
        with self._lock:
            self._sessions[id(session)] = session

    def unregister_session(self, session):
        if session is None:
            return
        with self._lock:
            self._sessions.pop(id(session), None)

    def request_stop(self):
        self._stop_event.set()
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            try:
                session.safe_quit()
            except Exception:
                continue


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
            options.add_argument('--autoplay-policy=no-user-gesture-required')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
        elif self.browser_type == 'firefox' and hasattr(options, 'set_preference'):
            options.set_preference('media.autoplay.default', 0)
            options.set_preference('media.autoplay.blocking_policy', 0)
            options.set_preference('dom.timeout.enable_budget_timer_throttling', False)
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

    def safe_quit(self):
        driver = self.driver
        self.driver = None
        if driver is None:
            return
        try:
            driver.quit()
        except Exception:
            pass

    def prompt_settings(self, notify=None):
        self.browser_type = choose_browser()
        emit_status(notify, 'info', '手动登录模式：浏览器窗口将最大化，请在浏览器中输入账号密码并完成验证。')

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

    def wait_for_manual_login_cli(self, notify=None):
        emit_status(notify, 'info', '请在浏览器中完成登录，并完成滑块验证。')
        emit_status(notify, 'info', '完成后切换回此窗口并按回车继续。')
        while True:
            input(ui_prompt('按回车继续...'))
            if self.check_login_success():
                emit_status(notify, 'success', '检测到已登录状态。')
                return True
            emit_status(notify, 'warn', '未检测到成功登录，请确认浏览器中的登录状态。')
            if not ask_yes_no('是否继续等待登录？'):
                return False

    def wait_for_manual_login(self, notify=None, wait_controller=None):
        if wait_controller is None:
            return self.wait_for_manual_login_cli(notify=notify)

        emit_status(notify, 'info', '请在浏览器中完成登录，并完成滑块验证。')
        emit_status(notify, 'info', '完成后在界面中点击“我已完成登录，开始检查”。')
        while True:
            action = wait_controller.wait_for_action(timeout=0.25)
            if action == 'cancel':
                emit_status(notify, 'warn', '登录流程已取消。')
                return False
            if action != 'check':
                continue
            if self.check_login_success():
                emit_status(notify, 'success', '检测到已登录状态。')
                return True
            emit_status(notify, 'warn', '未检测到成功登录，请确认浏览器中的登录状态。')

    def signin(self, notify=None, wait_controller=None):
        """执行登录流程并返回 cookie"""
        if wait_controller is None:
            ui_title('自动登录流程')
            self.prompt_settings(notify=notify)
        else:
            self.browser_type = normalize_browser_type(self.browser_type)
            emit_status(notify, 'info', f'当前浏览器: {self.browser_type.upper()}')

        try:
            emit_status(notify, 'progress', '正在创建浏览器驱动...')
            self.create_driver()
            emit_status(notify, 'success', '浏览器已启动。')
        except FileNotFoundError as e:
            emit_status(notify, 'error', f'错误: {e}')
            raise
        except Exception as e:
            emit_status(notify, 'error', f'浏览器启动失败: {e}')
            raise

        try:
            emit_status(notify, 'progress', '正在打开登录页面...')
            self.driver.get('https://v8.chaoxing.com')
            self.driver.maximize_window()  # 确保浏览器窗口最大化
            time.sleep(1)
            success = self.wait_for_manual_login(notify=notify, wait_controller=wait_controller)

            if not success:
                if wait_controller is not None and wait_controller.is_cancelled():
                    raise RuntimeError('登录已取消。')
                raise RuntimeError('登录失败，请检查浏览器中的登录状态。')

            cookie_string = self.get_cookie_string()
            emit_status(notify, 'success', f'Cookie 获取成功，长度: {len(cookie_string)}')
            return cookie_string
        except Exception as e:
            emit_status(notify, 'error', f'登录过程中出错: {e}')
            raise
        finally:
            emit_status(notify, 'info', '正在关闭浏览器...')
            try:
                self.driver.quit()
                emit_status(notify, 'success', '浏览器已关闭。')
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


def build_qa_context(client, model_name, temperature, base_messages):
    return {
        'client': client,
        'model_name': model_name,
        'temperature': temperature,
        'base_messages': list(base_messages or []),
        'qa_messages': [],
    }


def ask_followup(qa_context, question, notify=None):
    if not isinstance(qa_context, dict) or not qa_context.get('client'):
        raise ValueError('问答上下文不可用，请先完成一次作业解答。')

    user_input = str(question or '').strip()
    if not user_input:
        raise ValueError('请输入有效问题。')

    qa_messages = list(qa_context.get('qa_messages') or [])
    qa_messages.append({'role': 'user', 'content': user_input})
    qa_messages = _truncate_qa_history_if_needed(qa_messages)
    qa_context['qa_messages'] = qa_messages

    while True:
        messages = qa_context.get('base_messages', []) + qa_messages
        try:
            completion = qa_context['client'].chat.completions.create(
                model=qa_context['model_name'],
                temperature=qa_context['temperature'],
                messages=messages,
                stream=False,
            )
            answer_text = completion.choices[0].message.content or ''
            qa_messages.append({'role': 'assistant', 'content': answer_text})
            qa_messages = _truncate_qa_history_if_needed(qa_messages)
            qa_context['qa_messages'] = qa_messages
            return {
                'question': user_input,
                'answer': answer_text,
                'qa_context': qa_context,
            }
        except Exception as e:
            if _is_context_too_long_error(e):
                if len(qa_messages) >= 2:
                    qa_messages = qa_messages[2:]
                    qa_context['qa_messages'] = qa_messages
                    continue
                emit_status(notify, 'error', '上下文过长，无法在保留全文作业内容的情况下继续回答。')
                raise RuntimeError('上下文过长，请简化问题，或重新解题后再试。') from e
            emit_status(notify, 'error', f'问答请求失败: {e}')
            raise RuntimeError(f'问答请求失败: {e}') from e


def open_qa_loop(client_or_context, model_name=None, temperature=None, base_messages=None):
    if isinstance(client_or_context, dict) and client_or_context.get('client'):
        qa_context = client_or_context
    else:
        qa_context = build_qa_context(client_or_context, model_name, temperature, base_messages)

    ui_title('开放问答模式')
    ui_status('info', '输入问题即可继续提问，输入 exit/quit/退出/q 返回主菜单。')

    while True:
        user_input = input("\n你: ").strip()
        if not user_input:
            ui_status('warn', '请输入有效问题，或输入 exit/quit/退出/q 返回主菜单。')
            continue
        if _should_exit_qa(user_input):
            ui_status('success', '已退出开放问答模式，返回主菜单。')
            return

        try:
            result = ask_followup(qa_context, user_input, notify=ui_status)
            print("\nAI:")
            ui_block(result['answer'])
        except Exception as e:
            ui_status('error', str(e))


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


def run_manual_login(browser_type, notify=None, wait_controller=None):
    if wait_controller is None:
        raise ValueError('GUI 登录流程需要提供 wait_controller。')

    normalized_browser = normalize_browser_type(browser_type)
    session = BrowserSession(normalized_browser)
    cookie_value = session.signin(notify=notify, wait_controller=wait_controller)
    cookie_store.write(cookie_value)
    emit_status(notify, 'success', 'Cookie 已写入配置文件。')
    return {
        'cookie': cookie_value,
        'browser_type': normalized_browser,
    }


def build_request_headers(cookie_value):
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
        ),
        'Cookie': get_cookie_header_string(cookie_value),
    }


def create_ai_client(api_key):
    api_key_value = str(api_key or '').strip()
    if not api_key_value:
        raise ValueError('API 密钥不能为空。')
    return OpenAI(api_key=api_key_value, base_url='https://api.deepseek.com')


def _looks_like_login_page_html(page_html):
    lowered = str(page_html or '').lower()
    return (
        '<title>用户登录</title>' in str(page_html or '')
        or 'passport2-static.chaoxing.com' in lowered
        or 'id="loginbtn"' in lowered
        or 'name="uname"' in lowered
    )


def fetch_homework_page_via_browser(address, cookie_value, browser_type=DEFAULT_BROWSER, notify=None):
    normalized_browser = normalize_browser_type(browser_type)
    session = BrowserSession(normalized_browser)
    session.create_driver()
    driver = session.driver
    try:
        emit_status(notify, 'info', f'请求直连未拿到作业题页，正在切换到 {normalized_browser.upper()} 浏览器抓取页面...')
        inject_cookies_and_open(driver, address, cookie_value)
        _require_authenticated_page(driver)
        _wait_for_question_page(driver)
        return driver.page_source
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def fetch_homework_page(address, cookie_value, browser_type=None, notify=None):
    response = requests.get(address, headers=build_request_headers(cookie_value), timeout=15)
    response.raise_for_status()
    page_html = response.text
    if _looks_like_login_page_html(page_html):
        if browser_type is None:
            raise RuntimeError('请求作业页时仍被要求登录，请补充可用浏览器驱动后重试。')
        return fetch_homework_page_via_browser(
            address,
            cookie_value,
            browser_type=browser_type,
            notify=notify,
        )
    return page_html


def solve_homework_page_html(page_html, address, cookie, api_key, ai_mode, notify=None):
    address_value = str(address or '').lstrip('\ufeff').strip()
    cookie_value = str(cookie or '').strip()
    api_key_value = str(api_key or '').strip()

    if not address_value:
        raise ValueError('作业地址不能为空。')
    if not cookie_value:
        raise ValueError('Cookie 不能为空。')
    if not api_key_value:
        raise ValueError('API 密钥不能为空。')

    questions = extract_questions_from_page(page_html)
    if not questions:
        raise RuntimeError('未找到结构化题目，请检查页面地址、Cookie，或确认页面确实是作业答题页。')

    question_overview = format_questions_for_display(questions)
    type_summary = '、'.join(sorted({question['type_name'] for question in questions}))
    mode_choice = normalize_ai_mode(ai_mode)
    model_name = AI_MODE_MODEL_MAP[mode_choice]
    temperature = 0.0
    prompt = build_ai_prompt(questions)

    emit_status(notify, 'info', f'使用模型: {model_name} | 温度: {temperature}')
    emit_status(notify, 'progress', '正在生成答案...')

    try:
        client = create_ai_client(api_key_value)
        completion = client.chat.completions.create(
            model=model_name,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
            stream=False,
        )

        result_text = completion.choices[0].message.content or ''
        structured_answer = None
        structured_error = ''
        try:
            structured_answer = parse_ai_answer(
                result_text,
                questions,
                client=client,
                model_name=model_name,
                temperature=0.0,
            )
            emit_status(notify, 'success', f"已解析结构化答案，共 {len(structured_answer['answers'])} 题。")
        except Exception as parse_error:
            structured_error = str(parse_error)
            emit_status(notify, 'warn', f'结构化答案解析失败，暂时无法自动填写: {parse_error}')

        qa_context = build_qa_context(
            client,
            model_name,
            temperature,
            [
                {'role': 'user', 'content': f'作业题目结构如下：\n{question_overview}'},
                {'role': 'assistant', 'content': result_text},
            ],
        )

        return {
            'address': address_value,
            'cookie': cookie_value,
            'model_name': model_name,
            'temperature': temperature,
            'questions': questions,
            'question_overview': question_overview,
            'question_summary': {
                'count': len(questions),
                'type_summary': type_summary,
            },
            'raw_result': result_text,
            'structured_answer': structured_answer,
            'structured_error': structured_error,
            'qa_context': qa_context,
        }
    except Exception as exc:
        raise RuntimeError(f'API 请求失败: {exc}') from exc


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
    title_index = question_block.select_one('.Zy_TItle > i, .Zy_TItle i.fl')
    if title_index is not None:
        sources.append(title_index.get_text(' ', strip=True))
    for source in sources:
        match = re.search(r'(\d+)(?:\s*\.|\s*$)', str(source or '').strip())
        if match:
            return int(match.group(1))
    return None


def _extract_stem_text_from_candidate(candidate, question_no, type_name):
    if candidate is None:
        return ''

    candidate_soup = BeautifulSoup(str(candidate), 'html.parser')
    for selector in ('.newZy_TItle', '.colorShallow', '.mark_name_color'):
        for node in candidate_soup.select(selector):
            node.decompose()

    raw_text = clean_question_text(candidate_soup.get_text('\n', strip=True))
    if not raw_text:
        return ''

    filtered_lines = []
    type_tokens = {
        type_name,
        f'【{type_name}】',
        type_name.rstrip('题'),
        f'【{type_name.rstrip("题")}】' if type_name.endswith('题') else '',
    }
    type_tokens = {token for token in type_tokens if token}

    for line in raw_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        if question_no is not None and re.fullmatch(rf'{question_no}(?:\.)?', stripped):
            continue
        normalized_line = stripped.replace('（', '(').replace('）', ')')
        if stripped in type_tokens:
            continue
        if normalized_line.startswith('(') and type_name != '未知题型' and type_name.rstrip('题') in normalized_line:
            continue
        filtered_lines.append(stripped)
    return '\n'.join(filtered_lines).strip()


def extract_question_stem(question_block, question_no, type_name):
    header = question_block.find('h3')
    candidate_selectors = [
        'h3',
        '.Zy_TItle .fontLabel',
        '.fontLabel',
        '.mark_name',
        '.titTxt',
        '.CeYan_tiMu',
    ]

    if header is not None:
        paragraphs = []
        for paragraph in header.find_all('p'):
            text = clean_question_text(paragraph.get_text('\n', strip=True))
            if text:
                paragraphs.append(text)
        if paragraphs:
            return '\n'.join(paragraphs).strip()

    seen_nodes = set()
    for selector in candidate_selectors:
        for candidate in question_block.select(selector):
            node_key = id(candidate)
            if node_key in seen_nodes:
                continue
            seen_nodes.add(node_key)
            text = _extract_stem_text_from_candidate(candidate, question_no, type_name)
            if text:
                return text
    return ''


def extract_question_options(question_block, qid):
    options = []
    selector = (
        "div[onclick*='addChoice'], div[onclick*='addMultipleChoice'], "
        "li[onclick*='addChoice'], li[onclick*='addMultipleChoice']"
    )
    for option_el in question_block.select(selector):
        span = option_el.select_one(f"span.choice{qid}") or option_el.select_one("span[data]")
        if span is None:
            continue

        code = clean_question_text(span.get_text(' ', strip=True)).upper()
        value = clean_question_text(span.get('data') or code)
        answer_node = option_el.select_one('.answer_p, .after, a.after')
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


def _safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def _normalize_text(value):
    if value is None:
        return ''
    text = html_lib.unescape(str(value))
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_query_value(query, *keys):
    for key in keys:
        values = query.get(key) or query.get(key.lower()) or query.get(key.upper())
        if values:
            value = str(values[0]).strip()
            if value:
                return value
    return ''


def _build_task_id(task_type, *parts):
    normalized_parts = []
    for part in parts:
        piece = _normalize_text(part).replace(' ', '_')
        if piece:
            normalized_parts.append(piece)
    seed = '|'.join(normalized_parts) or str(time.time_ns())
    return f'{task_type}:{seed}'


def _coerce_course_item(course):
    if isinstance(course, CourseItem):
        return course
    if isinstance(course, dict):
        return CourseItem(
            course_name=course.get('course_name', ''),
            course_url=course.get('course_url', ''),
            courseid=course.get('courseid', ''),
            clazzid=course.get('clazzid', ''),
            cpi=course.get('cpi', ''),
            progress_text=course.get('progress_text', ''),
            status_text=course.get('status_text', ''),
        )
    raise TypeError('无效的课程数据。')


def _coerce_task_target(target):
    if isinstance(target, TaskTarget):
        return target
    if isinstance(target, dict):
        return TaskTarget(
            task_id=target.get('task_id') or _build_task_id(
                target.get('task_type', ''),
                target.get('courseid', ''),
                target.get('clazzid', ''),
                target.get('knowledge_id', '') or target.get('address', ''),
            ),
            task_type=target.get('task_type', ''),
            course_name=target.get('course_name', ''),
            title=target.get('title', ''),
            address=target.get('address', ''),
            course_url=target.get('course_url', ''),
            courseid=target.get('courseid', ''),
            clazzid=target.get('clazzid', ''),
            cpi=target.get('cpi', ''),
            enc=target.get('enc', ''),
            openc=target.get('openc', ''),
            knowledge_id=target.get('knowledge_id', ''),
            pending_count=_safe_int(target.get('pending_count', 0)),
            status_text=target.get('status_text', ''),
            submit_policy=target.get('submit_policy', 'manual'),
        )
    raise TypeError('无效的任务数据。')


def _is_login_url(url):
    lowered = str(url or '').lower()
    return any(token in lowered for token in ('login', 'passport', 'cas', 'verify'))


def _require_authenticated_page(driver):
    if _is_login_url(driver.current_url):
        raise RuntimeError('页面仍然跳转到登录页，Cookie 可能已失效。')


def _open_authenticated_address(driver, address, cookie_string, notify=None):
    emit_status(notify, 'progress', f'正在打开页面：{address}')
    inject_cookies_and_open(driver, address, cookie_string)
    _dismiss_runtime_alerts(driver, attempts=4, timeout=0.6)
    _require_authenticated_page(driver)
    return driver.current_url


def _safe_accept_alert(driver, timeout=1.5):
    try:
        alert = WebDriverWait(driver, timeout).until(EC.alert_is_present())
    except TimeoutException:
        return False
    alert.accept()
    time.sleep(0.3)
    return True


def _dismiss_runtime_alerts(driver, attempts=2, timeout=0.2):
    dismissed = False
    for _ in range(max(1, _safe_int(attempts, 1))):
        try:
            if not _safe_accept_alert(driver, timeout=timeout):
                break
        except Exception:
            break
        dismissed = True
    return dismissed


def _dismiss_course_popups(driver, notify=None):
    _dismiss_runtime_alerts(driver, attempts=4, timeout=0.4)
    popup_xpaths = [
        "//button[contains(., '开始学习')]",
        "//a[contains(., '开始学习')]",
        "//button[contains(., '继续学习')]",
        "//a[contains(., '继续学习')]",
        "//button[contains(., '我知道了')]",
        "//a[contains(., '我知道了')]",
        "//button[contains(., '同意')]",
        "//a[contains(., '同意')]",
        "//button[contains(., '关闭')]",
        "//span[contains(., '关闭')]",
    ]

    for _ in range(4):
        _dismiss_runtime_alerts(driver, attempts=2, timeout=0.2)
        clicked = False
        if _safe_accept_alert(driver, timeout=0.6):
            clicked = True
            emit_status(notify, 'info', '已处理弹窗确认。')

        driver.switch_to.default_content()
        for xpath in popup_xpaths:
            elements = driver.find_elements(By.XPATH, xpath)
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                        element,
                    )
                    time.sleep(0.8)
                    clicked = True
                    emit_status(notify, 'info', '已尝试关闭课程弹层。')
                    break
                except Exception:
                    continue
            if clicked:
                break

        if not clicked:
            break


def _is_element_visible(driver, element):
    try:
        return driver.execute_script(
            """
            const node = arguments[0];
            if (!node) {
                return false;
            }
            const style = window.getComputedStyle(node);
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
            """,
            element,
        )
    except Exception:
        try:
            return element.is_displayed()
        except Exception:
            return False


def _switch_to_content_frame(driver, frame_id, timeout=FRAME_READY_TIMEOUT):
    _dismiss_runtime_alerts(driver)
    driver.switch_to.default_content()
    WebDriverWait(driver, timeout).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, frame_id))
    )
    _dismiss_runtime_alerts(driver)
    try:
        wait_for_page_ready(driver, timeout=min(timeout, PAGE_READY_TIMEOUT))
    except TimeoutException:
        pass


def _switch_to_course_tab_frame(driver, dataname, timeout=FRAME_READY_TIMEOUT):
    def locate(current_driver):
        current_driver.switch_to.default_content()
        frames = current_driver.find_elements(By.CSS_SELECTOR, "iframe[id^='frame_content']")
        if not frames:
            return None

        for frame in frames:
            frame_id = (frame.get_attribute('id') or '').lower()
            if dataname and dataname in frame_id:
                return frame

        visible_frames = [frame for frame in frames if _is_element_visible(current_driver, frame)]
        if len(visible_frames) == 1:
            return visible_frames[0]
        if len(frames) == 1:
            return frames[0]
        return None

    frame = WebDriverWait(driver, timeout).until(locate)
    frame_id = frame.get_attribute('id') or ''
    driver.switch_to.default_content()
    driver.switch_to.frame(frame)
    try:
        wait_for_page_ready(driver, timeout=min(timeout, PAGE_READY_TIMEOUT))
    except TimeoutException:
        pass
    return frame_id


def _click_course_tab(driver, dataname, notify=None):
    driver.switch_to.default_content()
    link = None
    selectors = [
        f"li[dataname='{dataname}'] a",
        f"li[dataname='{dataname}']",
        f"[data-name='{dataname}'] a",
    ]
    for selector in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            link = elements[0]
            break

    if link is None:
        return _switch_to_course_tab_frame(driver, dataname)

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
    time.sleep(0.2)
    try:
        link.click()
    except Exception:
        driver.execute_script('arguments[0].click();', link)
    time.sleep(0.6)
    emit_status(notify, 'info', f'已切换到课程页签：{dataname}')
    return _switch_to_course_tab_frame(driver, dataname)


def parse_course_catalog_html(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    courses = []
    seen_urls = set()

    for anchor in soup.select("a.color1[href*='visit/stucoursemiddle'], a[href*='visit/stucoursemiddle']"):
        href = _normalize_text(anchor.get('href'))
        if not href:
            continue
        href = urljoin(PERSONAL_SPACE_URL, href)
        if href in seen_urls:
            continue

        query = parse_qs(urlparse(href).query)
        courseid = _extract_query_value(query, 'courseid')
        clazzid = _extract_query_value(query, 'clazzid')
        cpi = _extract_query_value(query, 'cpi')
        course_name = _normalize_text(anchor.get_text(' ', strip=True))
        if not (course_name and courseid and clazzid):
            continue

        container = (
            anchor.find_parent('li')
            or anchor.find_parent('div', class_=re.compile(r'(course|Mcon|online|list|item)', re.IGNORECASE))
            or anchor.parent
        )
        container_text = _normalize_text(container.get_text('\n', strip=True) if container else '')
        progress_match = re.search(r'(任务点进度[:：]?\s*[^\n]+)', container_text)
        status_match = re.search(r'(进行中|已完成|未开始|待批阅|待完成|已结束)', container_text)

        courses.append(CourseItem(
            course_name=course_name,
            course_url=href,
            courseid=courseid,
            clazzid=clazzid,
            cpi=cpi,
            progress_text=progress_match.group(1) if progress_match else '',
            status_text=status_match.group(1) if status_match else '',
        ))
        seen_urls.add(href)

    return courses


def parse_course_page_context(page_html, current_url=''):
    soup = BeautifulSoup(page_html, 'html.parser')
    parsed_current = parse_qs(urlparse(current_url).query)

    def input_value(*names):
        for name in names:
            node = soup.select_one(f"input[name='{name}'], input#{name}")
            if node is not None:
                value = _normalize_text(node.get('value'))
                if value:
                    return value
        return ''

    title = ''
    preferred_selectors = (
        '.course-name',
        '.courseName',
        '.course-name-box',
        '.catalog_name',
        '.catalogName',
    )
    for selector in preferred_selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        candidate = _normalize_text(node.get_text(' ', strip=True))
        if candidate and '位置指引' not in candidate and '下载中心' not in candidate:
            title = candidate
            break

    if not title and soup.title and soup.title.string:
        candidate = _normalize_text(str(soup.title.string).replace('- 超星学习通', ''))
        if candidate:
            title = candidate

    if not title:
        title_node = soup.select_one('h1, h2, h3')
        if title_node is not None:
            candidate = _normalize_text(title_node.get_text(' ', strip=True))
            if candidate and '位置指引' not in candidate and '下载中心' not in candidate:
                title = candidate

    tabs = {}
    for node in soup.select('li[dataname]'):
        dataname = _normalize_text(node.get('dataname')).lower()
        if dataname not in {'zj', 'zy', 'ks'}:
            continue
        anchor = node.select_one('a')
        data_url = _normalize_text(anchor.get('data-url') if anchor else '')
        if data_url:
            tabs[dataname] = urljoin(current_url or PERSONAL_SPACE_URL, data_url)

    return {
        'course_name': title,
        'courseid': input_value('courseid', 'courseId') or _extract_query_value(parsed_current, 'courseid', 'courseId'),
        'clazzid': input_value('clazzid', 'clazzId') or _extract_query_value(parsed_current, 'clazzid', 'clazzId'),
        'cpi': input_value('cpi') or _extract_query_value(parsed_current, 'cpi'),
        'enc': input_value('enc', 'stuenc'),
        'openc': input_value('openc'),
        'tabs': tabs,
    }


def parse_studentcourse_html(page_html, course_meta):
    course = _coerce_course_item(course_meta)
    soup = BeautifulSoup(page_html, 'html.parser')
    study_enc_match = re.search(r'var\s+enc\s*=\s*"([^"]+)"', page_html)
    study_cpi_match = re.search(r'var\s+cpi\s*=\s*"?(\d+)"?', page_html)
    course_enc = getattr(course, 'enc', '')
    course_openc = getattr(course, 'openc', '')
    study_enc = study_enc_match.group(1) if study_enc_match else course_enc
    study_cpi = study_cpi_match.group(1) if study_cpi_match else course.cpi

    targets = []
    for node in soup.select(".chapter_item[onclick*='toOld(']"):
        onclick = html_lib.unescape(node.get('onclick') or '')
        match = re.search(
            r"toOld\('(?P<courseid>[^']+)'\s*,\s*'(?P<knowledgeid>[^']+)'\s*,\s*'(?P<clazzid>[^']+)'\s*,\s*(?P<hidetype>[^)]+)\)",
            onclick,
        )
        if not match:
            continue

        courseid = _normalize_text(match.group('courseid'))
        clazzid = _normalize_text(match.group('clazzid'))
        knowledge_id = _normalize_text(match.group('knowledgeid'))
        hidetype = _safe_int(match.group('hidetype'))
        title = _normalize_text(node.get('title')) or _normalize_text(node.get_text(' ', strip=True))
        job_count_node = node.select_one('.knowledgeJobCount')
        orange_node = node.select_one('.orangeNew')
        pending_count = max(
            _safe_int(job_count_node.get('value') if job_count_node else 0),
            _safe_int(orange_node.get_text(strip=True) if orange_node else 0),
        )
        status_text = _normalize_text(node.get_text(' ', strip=True))
        address = (
            f"https://mooc1.chaoxing.com/mycourse/studentstudy"
            f"?chapterId={quote(knowledge_id)}"
            f"&courseId={quote(courseid)}"
            f"&clazzid={quote(clazzid)}"
            f"&cpi={quote(str(study_cpi))}"
            f"&enc={quote(study_enc)}"
            f"&mooc2=1"
            f"&hidetype={hidetype}"
        )
        if course.openc:
            address += f"&openc={quote(course.openc)}"

        targets.append(TaskTarget(
            task_id=_build_task_id('chapter', courseid, clazzid, knowledge_id),
            task_type='chapter',
            course_name=course.course_name,
            title=title,
            address=address,
            course_url=course.course_url,
            courseid=courseid,
            clazzid=clazzid,
            cpi=str(study_cpi),
            enc=study_enc,
            openc=course_openc,
            knowledge_id=knowledge_id,
            pending_count=pending_count,
            status_text=status_text,
            submit_policy='auto_submit',
        ))

    return targets


def parse_work_list_html(page_html, course_meta, task_type='homework'):
    course = _coerce_course_item(course_meta)
    soup = BeautifulSoup(page_html, 'html.parser')
    candidates = soup.select('li[data], li[data-url], tr[data], div[data][onclick]')
    targets = []
    seen_addresses = set()

    for node in candidates:
        raw_address = (
            node.get('data')
            or node.get('data-url')
            or node.get('href')
            or ''
        )
        address = urljoin('https://mooc1.chaoxing.com', _normalize_text(raw_address))
        if not address or address in seen_addresses:
            continue
        if not any(token in address for token in ('/work/task', '/exam/', 'exam-list', 'work/task')):
            continue

        title = ''
        for text_node in node.select('.right-content p, p, h3, h4, .title, a'):
            text = _normalize_text(text_node.get_text(' ', strip=True))
            if not text or text in {'待批阅', '已完成', '未开始', '进行中'}:
                continue
            title = text
            break
        if not title:
            title = _normalize_text(node.get_text(' ', strip=True))

        status_node = (
            node.select_one('.status')
            or node.select_one('.tag')
            or node.select_one('.state')
        )
        status_text = _normalize_text(status_node.get_text(' ', strip=True) if status_node else '')
        query = parse_qs(urlparse(address).query)
        key = (
            _extract_query_value(query, 'workId', 'examId', 'paperId')
            or _extract_query_value(query, 'answerId', 'taskref', 'taskId')
            or address
        )

        targets.append(TaskTarget(
            task_id=_build_task_id(task_type, course.courseid, course.clazzid, key),
            task_type=task_type,
            course_name=course.course_name,
            title=title,
            address=address,
            course_url=course.course_url,
            courseid=course.courseid,
            clazzid=course.clazzid,
            cpi=course.cpi,
            enc=getattr(course, 'enc', ''),
            openc=getattr(course, 'openc', ''),
            status_text=status_text,
            submit_policy='manual',
        ))
        seen_addresses.add(address)

    return targets


def parse_chapter_card_html(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    nested_iframe = soup.select_one("iframe[objectid], iframe[_src], iframe[jobid], iframe[src]")
    task_type = 'unknown'
    task_url = ''
    duration = 0
    detail = ''

    if nested_iframe is not None:
        object_id = _normalize_text(nested_iframe.get('objectid'))
        job_id = _normalize_text(nested_iframe.get('jobid'))
        raw_task_url = _normalize_text(nested_iframe.get('_src') or nested_iframe.get('src'))
        iframe_classes = ' '.join(nested_iframe.get('class', []))
        raw_attach_data = _normalize_text(nested_iframe.get('data'))
        attach_type = ''
        attach_name = ''
        if raw_attach_data:
            try:
                attach_data = json.loads(raw_attach_data)
                attach_type = _normalize_text(attach_data.get('type'))
                attach_name = _normalize_text(attach_data.get('name'))
            except Exception:
                attach_type = ''
                attach_name = ''
        task_url = urljoin('https://mooc1.chaoxing.com', raw_task_url)
        lowered_task_url = task_url.lower()
        lowered_classes = iframe_classes.lower()
        lowered_attach_type = attach_type.lower()
        is_document_module = (
            '/modules/pdf/' in lowered_task_url
            or '/modules/doc/' in lowered_task_url
            or '/modules/ppt/' in lowered_task_url
            or '/modules/book/' in lowered_task_url
            or 'insertdoc' in lowered_classes
            or lowered_attach_type in {'.pdf', '.ppt', '.pptx', '.doc', '.docx', '.txt'}
        )
        if is_document_module:
            task_type = 'document'
            detail = attach_name or attach_type or '文档任务'
        elif object_id:
            task_type = 'video'
        elif job_id.startswith('work-') or '/api/work' in raw_task_url:
            task_type = 'quiz'

    if task_type == 'unknown':
        if re.search(r'"type":"video"', page_html):
            task_type = 'video'
        elif re.search(r'insertdoc-online|modules/pdf|modules/doc|modules/ppt|modules/book|"type":"\.(pdf|ppt|pptx|doc|docx|txt)"', page_html, re.IGNORECASE):
            task_type = 'document'
        elif re.search(r'"/mooc-ans/api/work|"_src":"?/mooc-ans/api/work|"module":"work"', page_html):
            task_type = 'quiz'

    duration_match = re.search(r'"attDuration"\s*:\s*(\d+)', page_html)
    if duration_match:
        duration = _safe_int(duration_match.group(1))

    issue_selectors = (
        '.tipStyle',
        '#note',
        '#note1',
        '#note1-wrap',
        '.nullpage dd',
    )
    for selector in issue_selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        text = _normalize_text(node.get_text(' ', strip=True))
        if text:
            detail = text
            break

    unfinished = False
    icons = soup.select('.ans-job-icon')
    if icons:
        unfinished = any(
            'ans-job-finished' not in ((icon.parent.get('class', []) if icon.parent else []))
            for icon in icons
        )

    return {
        'kind': task_type,
        'task_url': task_url,
        'duration': duration,
        'unfinished': unfinished,
        'detail': detail,
    }


def _extract_course_center_url(page_html):
    if not page_html:
        return ''

    soup = BeautifulSoup(page_html, 'html.parser')
    selector_candidates = [
        "[dataurl*='visit/interaction']",
        "[data-url*='visit/interaction']",
        "a[href*='visit/interaction']",
        "iframe[src*='visit/interaction']",
    ]
    for selector in selector_candidates:
        for node in soup.select(selector):
            raw_url = (
                node.get('dataurl')
                or node.get('data-url')
                or node.get('href')
                or node.get('src')
                or ''
            )
            url = html_lib.unescape(_normalize_text(raw_url))
            if 'visit/interaction' in url:
                return urljoin(PERSONAL_SPACE_URL, url)

    for match in re.finditer(r"https://[^'\"<>\s]+/visit/interaction[^'\"<>\s]*", page_html, re.IGNORECASE):
        return html_lib.unescape(match.group(0))
    return ''


def _wait_for_course_catalog_ready(driver, timeout=FRAME_READY_TIMEOUT):
    def locate(current_driver):
        anchors = current_driver.find_elements(By.CSS_SELECTOR, "a[href*='visit/stucoursemiddle']")
        visible = [anchor for anchor in anchors if _normalize_text(anchor.text)]
        if visible:
            return visible

        body_text = _normalize_text(current_driver.find_element(By.TAG_NAME, 'body').text)
        if '添加课程' in body_text and '课程' in (current_driver.title or ''):
            return anchors or [body_text]
        return None

    return WebDriverWait(driver, timeout).until(locate)


def load_course_catalog(cookie, browser_type, notify=None):
    cookie_value = str(cookie or '').strip()
    if not cookie_value:
        raise ValueError('Cookie 不能为空。')

    normalized_browser = normalize_browser_type(browser_type)
    session = BrowserSession(normalized_browser)
    session.create_driver()
    driver = session.driver
    try:
        _open_authenticated_address(driver, PERSONAL_SPACE_URL, cookie_value, notify=notify)
        _dismiss_course_popups(driver, notify=notify)
        driver.switch_to.default_content()
        page_html = driver.page_source
        courses = parse_course_catalog_html(page_html)
        if not courses:
            course_center_url = _extract_course_center_url(page_html)
            if course_center_url:
                emit_status(notify, 'info', '已定位课程中心入口，正在载入课程列表...')
                _open_authenticated_address(driver, course_center_url, cookie_value, notify=notify)
                _dismiss_course_popups(driver, notify=notify)
                try:
                    _wait_for_course_catalog_ready(driver)
                except TimeoutException:
                    pass
                page_html = driver.page_source
                courses = parse_course_catalog_html(page_html)
        if not courses:
            try:
                _switch_to_content_frame(driver, PERSONAL_SPACE_IFRAME_ID)
                page_html = driver.page_source
                courses = parse_course_catalog_html(page_html)
            except Exception:
                driver.switch_to.default_content()
        if not courses:
            raise RuntimeError('未能从个人空间载入课程列表，请重新获取 Cookie 后再试。')
        emit_status(notify, 'success', f'已发现 {len(courses)} 门课程。')
        return courses
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def load_course_task_catalog(course_url, cookie, browser_type, notify=None):
    course_url_value = str(course_url or '').strip()
    cookie_value = str(cookie or '').strip()
    if not course_url_value:
        raise ValueError('课程地址不能为空。')
    if not cookie_value:
        raise ValueError('Cookie 不能为空。')

    normalized_browser = normalize_browser_type(browser_type)
    session = BrowserSession(normalized_browser)
    session.create_driver()
    driver = session.driver
    try:
        _open_authenticated_address(driver, course_url_value, cookie_value, notify=notify)
        _dismiss_course_popups(driver, notify=notify)

        context = parse_course_page_context(driver.page_source, driver.current_url)
        course_item = CourseItem(
            course_name=context.get('course_name') or _normalize_text(driver.title).replace('- 超星学习通', ''),
            course_url=course_url_value,
            courseid=context.get('courseid', ''),
            clazzid=context.get('clazzid', ''),
            cpi=context.get('cpi', ''),
            progress_text='',
            status_text='',
        )
        chapter_course = CourseItem(
            course_name=course_item.course_name,
            course_url=course_item.course_url,
            courseid=course_item.courseid,
            clazzid=course_item.clazzid,
            cpi=course_item.cpi,
            progress_text='',
            status_text='',
        )
        chapter_course.enc = context.get('enc', '')  # 动态属性，便于后续复用
        chapter_course.openc = context.get('openc', '')

        catalog = {
            'course': course_item,
            'chapters': [],
            'homework': [],
            'exams': [],
        }

        tab_specs = (
            ('zj', 'chapters', '章节', lambda html: parse_studentcourse_html(html, chapter_course)),
            ('zy', 'homework', '作业', lambda html: parse_work_list_html(html, chapter_course, task_type='homework')),
            ('ks', 'exams', '考试', lambda html: parse_work_list_html(html, chapter_course, task_type='exam')),
        )

        for dataname, key, label, parser in tab_specs:
            try:
                _click_course_tab(driver, dataname, notify=notify)
                page_html = driver.page_source
                catalog[key] = parser(page_html)
                emit_status(notify, 'success', f'{course_item.course_name}：已载入{label} {len(catalog[key])}项。')
            except Exception as exc:
                emit_status(notify, 'warn', f'{course_item.course_name}：载入{label}失败：{exc}')
                catalog[key] = []
            finally:
                driver.switch_to.default_content()

        return catalog
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _prefix_notify(notify, prefix):
    if not callable(notify):
        return None

    def wrapped(level, message):
        notify(level, f'{prefix}{message}')

    return wrapped


def _emit_parallel_event(event_callback, payload):
    if not callable(event_callback):
        return
    try:
        event_callback(payload)
    except Exception:
        return


def _stop_requested(parallel_controller=None):
    return bool(parallel_controller and parallel_controller.stop_requested())


def _raise_if_parallel_stopped(parallel_controller=None):
    if _stop_requested(parallel_controller):
        raise ParallelStopRequested('并发任务已停止。')


def _sleep_with_parallel_stop(seconds, parallel_controller=None, interval=0.2):
    deadline = time.time() + max(float(seconds or 0), 0.0)
    while True:
        _raise_if_parallel_stopped(parallel_controller)
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(interval, remaining))


def _build_stopped_result(target, browser_type, detail='任务已停止。'):
    normalized_target = _coerce_task_target(target)
    return TaskRunResult(
        task_id=normalized_target.task_id,
        task_type=normalized_target.task_type,
        course_name=normalized_target.course_name,
        title=normalized_target.title,
        status='stopped',
        retries=0,
        kept_open=False,
        detail=detail,
        address=normalized_target.address,
        browser_type=normalize_browser_type(browser_type),
        answer_count=0,
        raw_result='',
    )


def _is_focus_sensitive_target(target):
    normalized_target = _coerce_task_target(target)
    return normalized_target.task_type in FOCUS_SENSITIVE_TASK_TYPES


def _resolve_parallel_strategy(targets, requested_parallel):
    normalized_targets = [_coerce_task_target(item) for item in list(targets or [])]
    requested = max(1, _safe_int(requested_parallel, DEFAULT_PARALLEL_LIMIT) or DEFAULT_PARALLEL_LIMIT)
    has_focus_sensitive = any(_is_focus_sensitive_target(target) for target in normalized_targets)
    if not has_focus_sensitive:
        return {
            'regular_limit': requested,
            'focus_limit': 0,
            'worker_limit': requested,
            'note': '',
        }
    return {
        'regular_limit': requested,
        'focus_limit': 1,
        'worker_limit': requested + 1,
        'note': '检测到章节视频类任务：章节将单独串行排队执行，作业/考试继续按并发槽位运行。',
    }


def _wait_for_question_page(driver, timeout=PAGE_READY_TIMEOUT):
    try:
        wait_for_page_ready(driver, timeout=timeout)
    except TimeoutException:
        pass
    WebDriverWait(driver, timeout).until(
        lambda current_driver: (
            current_driver.find_elements(By.CSS_SELECTOR, 'div.singleQuesId')
            or 'singleQuesId' in current_driver.page_source
        )
    )


def _current_card_has_pending_job(driver):
    _dismiss_runtime_alerts(driver)
    driver.switch_to.default_content()
    try:
        result = driver.execute_script(
            "return typeof checkJob === 'function' ? Boolean(checkJob()) : null;"
        )
        if result is not None:
            return bool(result)
    except Exception:
        pass

    _switch_to_content_frame(driver, CHAPTER_IFRAME_ID)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.switch_to.default_content()
    icons = soup.select('.ans-job-icon')
    if not icons:
        return False
    for icon in icons:
        parent = icon.parent
        classes = parent.get('class', []) if parent else []
        if 'ans-job-finished' not in classes:
            return True
    return False


def _get_chapter_pending_count(driver, knowledge_id):
    driver.switch_to.default_content()
    text = driver.execute_script(
        """
        const node = document.querySelector(arguments[0]);
        return node ? (node.textContent || '') : '';
        """,
        f'#cur{knowledge_id} .orangeNew',
    )
    return _safe_int(text, 0)


def _get_chapter_card_count(driver):
    driver.switch_to.default_content()
    return len(driver.find_elements(By.CSS_SELECTOR, '#prev_tab .prev_ul li'))


def _load_chapter_card(driver, target, index, total_count, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    driver.switch_to.default_content()
    changed = False
    try:
        changed = bool(driver.execute_script(
            """
            if (typeof changeDisplayContent !== 'function') {
                return false;
            }
            changeDisplayContent(arguments[0], arguments[1], arguments[2], arguments[3], arguments[4], '', '');
            return true;
            """,
            index,
            total_count,
            target.knowledge_id,
            target.courseid,
            target.clazzid,
        ))
    except Exception:
        changed = False

    if not changed:
        card = WebDriverWait(driver, FRAME_READY_TIMEOUT).until(
            lambda current_driver: current_driver.find_element(By.CSS_SELECTOR, f'#prev_tab .prev_ul li:nth-child({index})')
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        try:
            card.click()
        except Exception:
            driver.execute_script('arguments[0].click();', card)

    _sleep_with_parallel_stop(0.8, parallel_controller=parallel_controller)
    _switch_to_content_frame(driver, CHAPTER_IFRAME_ID)
    driver.switch_to.default_content()


def _detect_current_card_task(driver):
    driver.switch_to.default_content()
    active_title = driver.execute_script(
        """
        const active = document.querySelector('#prev_tab .prev_ul li.active');
        if (!active) {
            return '';
        }
        return active.getAttribute('title') || active.textContent || '';
        """
    )
    unfinished = _current_card_has_pending_job(driver)

    _switch_to_content_frame(driver, CHAPTER_IFRAME_ID)
    page_html = driver.page_source
    driver.switch_to.default_content()
    parsed = parse_chapter_card_html(page_html)

    return {
        'kind': parsed.get('kind', 'unknown'),
        'task_url': parsed.get('task_url', ''),
        'title': _normalize_text(active_title),
        'unfinished': unfinished,
        'duration': parsed.get('duration', 0),
        'detail': parsed.get('detail', ''),
    }


def _ensure_video_playing(driver, playback_rate=DEFAULT_CHAPTER_VIDEO_PLAYBACK_RATE, allow_button_click=False):
    _switch_to_content_frame(driver, CHAPTER_IFRAME_ID)
    video_frame = WebDriverWait(driver, 12).until(
        lambda current_driver: current_driver.find_element(By.CSS_SELECTOR, "iframe[objectid], iframe[jobid]")
    )
    driver.switch_to.frame(video_frame)
    WebDriverWait(driver, 12).until(
        lambda current_driver: current_driver.find_elements(By.CSS_SELECTOR, 'video, .vjs-big-play-button, .vjs-play-control')
    )
    state = driver.execute_script(
        """
        const rate = Number(arguments[0]) || 1;
        const allowButtonClick = Boolean(arguments[1]);
        const video = document.querySelector('video');
        const playButton = document.querySelector('.vjs-big-play-button, .vjs-play-control');
        if (!video) {
            return { ok: false, clickedButton: false };
        }
        try {
            window.focus();
            if (window.top && window.top !== window) {
                window.top.focus();
            }
        } catch (error) {}
        const applyVisibleState = (target) => {
            if (!target) {
                return;
            }
            const descriptors = [
                ['hidden', false],
                ['webkitHidden', false],
                ['visibilityState', 'visible'],
                ['webkitVisibilityState', 'visible'],
            ];
            for (const [key, value] of descriptors) {
                try {
                    Object.defineProperty(target, key, {
                        configurable: true,
                        get: () => value,
                    });
                } catch (error) {}
            }
        };
        applyVisibleState(document);
        applyVisibleState(window.document);
        try {
            const interactiveNode = document.body || document.documentElement;
            if (interactiveNode) {
                ['mouseenter', 'mouseover', 'mousemove'].forEach((eventName) => {
                    interactiveNode.dispatchEvent(new MouseEvent(eventName, {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: 32,
                        clientY: 32,
                    }));
                });
            }
        } catch (error) {}
        video.muted = true;
        video.defaultMuted = true;
        video.autoplay = true;
        video.volume = 0;
        try {
            video.setAttribute('muted', 'muted');
            video.setAttribute('autoplay', 'autoplay');
            video.playbackRate = rate;
        } catch (error) {}
        const dispatchClick = (target) => {
            if (!target) {
                return false;
            }
            try {
                ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((eventName) => {
                    target.dispatchEvent(new MouseEvent(eventName, {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }));
                });
                return true;
            } catch (error) {
                return false;
            }
        };
        let clickedButton = false;
        try {
            if (video.paused) {
                video.play();
            }
        } catch (error) {}
        try {
            if (allowButtonClick && video.paused && playButton) {
                const title = String(playButton.getAttribute('title') || playButton.getAttribute('aria-label') || '');
                const className = String(playButton.className || '');
                const shouldClick = (
                    !video.ended
                    && (
                        !Number(video.duration || 0)
                        || Number(video.currentTime || 0) < Math.max(Number(video.duration || 0) - 1, 0)
                    )
                    && (
                        className.includes('vjs-big-play-button')
                        || className.includes('vjs-paused')
                        || title.includes('\u64ad\u653e')
                        || title.toLowerCase().includes('play')
                    )
                );
                if (shouldClick) {
                    clickedButton = dispatchClick(playButton);
                    if (!clickedButton) {
                        playButton.click();
                        clickedButton = true;
                    }
                }
                if (video.paused) {
                    clickedButton = dispatchClick(video) || clickedButton;
                }
            }
        } catch (error) {}
        try {
            if (video.paused) {
                video.play();
            }
        } catch (error) {}
        return {
            ok: true,
            paused: !!video.paused,
            ended: !!video.ended,
            currentTime: Number(video.currentTime || 0),
            duration: Number(video.duration || 0),
            playbackRate: Number(video.playbackRate || rate),
            clickedButton,
        };
        """,
        playback_rate,
        allow_button_click,
    )
    driver.switch_to.default_content()
    return state


def _is_video_near_end(current_time, duration):
    duration = float(duration or 0)
    current_time = float(current_time or 0)
    if duration <= 1:
        return False
    return current_time >= max(duration - 2, duration * 0.96)


def _ensure_video_playing_with_retry(driver, playback_rate, allow_button_click=False, retries=3, notify=None):
    last_error = None
    for attempt in range(max(1, _safe_int(retries, 1))):
        try:
            return _ensure_video_playing(
                driver,
                playback_rate=playback_rate,
                allow_button_click=allow_button_click,
            )
        except (TimeoutException, UnexpectedAlertPresentException) as exc:
            last_error = exc
            _dismiss_runtime_alerts(driver, attempts=3, timeout=0.3)
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            if attempt + 1 < max(1, _safe_int(retries, 1)):
                emit_status(notify, 'warn', '视频播放框架短暂失联，正在重试恢复播放...')
                time.sleep(1.0)
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError('未能恢复视频播放。')


def _raise_document_manual_review(card_info, target):
    card_title = card_info.get('title') or target.title
    detail = _normalize_text(card_info.get('detail'))
    message = f'章节任务点“{card_title}”是文档/PDF任务，当前不走视频播放逻辑。'
    if detail:
        message += f' 当前页面提示：{detail}'
    raise ManualReviewRequired(message)


def _play_video_card(driver, target, card_info, notify=None, parallel_controller=None):
    expected_duration = max(_safe_int(card_info.get('duration', 0)), 1)
    playback_rate = DEFAULT_CHAPTER_VIDEO_PLAYBACK_RATE
    timeout = min(
        DEFAULT_VIDEO_WAIT_SECONDS,
        max(120, int(expected_duration / max(playback_rate, 1.0)) + 180),
    )
    deadline = time.time() + timeout
    last_emit = 0.0
    first_start_attempt = True
    playback_started = False
    resume_with_button = False
    last_resume_log = 0.0
    last_progress_time = time.time()
    last_progress_position = 0.0
    low_speed_fallback_applied = playback_rate <= 1.0
    frame_recovery_count = 0

    while time.time() < deadline:
        _raise_if_parallel_stopped(parallel_controller)
        try:
            state = _ensure_video_playing_with_retry(
                driver,
                playback_rate=playback_rate,
                allow_button_click=first_start_attempt or resume_with_button,
                notify=notify,
            )
            frame_recovery_count = 0
        except TimeoutException:
            frame_recovery_count += 1
            if not low_speed_fallback_applied and playback_rate > 1.0:
                playback_rate = 1.0
                low_speed_fallback_applied = True
                emit_status(notify, 'warn', '检测到视频框架不稳定，已自动降为 1 倍速后继续尝试。')
            emit_status(
                notify,
                'warn',
                (
                    f'视频任务点框架暂时失联，正在刷新页面恢复播放'
                    f"（第 {frame_recovery_count} 次）：{card_info.get('title') or target.title}"
                ),
            )
            driver.switch_to.default_content()
            driver.refresh()
            try:
                wait_for_page_ready(driver, timeout=PAGE_READY_TIMEOUT)
            except TimeoutException:
                pass
            _dismiss_course_popups(driver, notify=notify)
            _sleep_with_parallel_stop(1.0, parallel_controller=parallel_controller)
            continue
        if first_start_attempt:
            first_start_attempt = False
        now = time.time()
        current_time = float(state.get('currentTime') or 0)
        duration = float(state.get('duration') or expected_duration)
        near_end = _is_video_near_end(current_time, duration)
        is_paused = bool(state.get('paused', True))
        if current_time > 0.5 or (not is_paused and duration > 1 and current_time > 0):
            playback_started = True
        if current_time > last_progress_position + 0.4:
            last_progress_position = current_time
            last_progress_time = now

        not_started_timeout = (
            not playback_started
            and not near_end
            and (now - last_progress_time) >= max(6.0, VIDEO_STATUS_POLL_INTERVAL * 2)
        )
        stalled = playback_started and not near_end and (now - last_progress_time) >= max(8.0, VIDEO_STATUS_POLL_INTERVAL * 2)
        resume_with_button = (
            not near_end
            and (is_paused or stalled or not_started_timeout)
        )
        if (stalled or not_started_timeout) and not low_speed_fallback_applied and playback_rate > 1.0:
            playback_rate = 1.0
            low_speed_fallback_applied = True
            emit_status(notify, 'warn', '检测到视频播放不稳定，已自动降为 1 倍速继续播放。')
        if resume_with_button:
            if now - last_resume_log >= 10:
                reason = '视频暂停'
                if stalled and not is_paused:
                    reason = '视频进度长时间未前进'
                elif not_started_timeout:
                    reason = '视频未能自动开始播放'
                emit_status(
                    notify,
                    'warn',
                    (
                        f'检测到{reason}，正在尝试恢复播放：'
                        f'{card_info.get("title") or target.title}'
                    ),
                )
                last_resume_log = now

        if not _current_card_has_pending_job(driver):
            completion_reason = '检测到任务点已从待完成状态移除，判定视频任务完成。'
            emit_status(
                notify,
                'success',
                f'视频任务完成：{card_info.get("title") or target.title}（{completion_reason}）',
            )
            return completion_reason

        if now - last_emit >= 20:
            current_time = _safe_int(current_time)
            total_time = _safe_int(state.get('duration', expected_duration))
            emit_status(
                notify,
                'progress',
                (
                    f'视频播放中：{card_info.get("title") or target.title} '
                    f'({current_time}s / {total_time}s，{playback_rate:.1f}x)'
                ),
            )
            last_emit = now
        _sleep_with_parallel_stop(VIDEO_STATUS_POLL_INTERVAL, parallel_controller=parallel_controller)

    raise RuntimeError(f'视频任务超时未完成：{card_info.get("title") or target.title}')


def _open_new_tab(driver):
    before = set(driver.window_handles)
    driver.execute_script("window.open('about:blank', '_blank');")
    WebDriverWait(driver, 10).until(lambda current_driver: len(current_driver.window_handles) > len(before))
    after = set(driver.window_handles)
    return next(iter(after - before))


def is_chapter_quiz_address(address):
    parsed = urlparse(str(address or '').strip())
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    old_work_id = _extract_query_value(query, 'oldWorkId')
    origin_job_id = _extract_query_value(query, 'originJobId')
    job_id = _extract_query_value(query, 'jobid')
    knowledge_id = _extract_query_value(query, 'knowledgeid')

    if '/mooc-ans/api/work' in path:
        return bool(origin_job_id or old_work_id or (knowledge_id and str(job_id).startswith('work-')))
    if '/mooc-ans/work/dohomeworknew' in path:
        return bool(origin_job_id or old_work_id or (knowledge_id and str(job_id).startswith('work-')))
    return False


def _is_work_answer_page_url(address):
    path = urlparse(str(address or '').strip()).path.lower()
    return '/mooc-ans/api/work' in path or '/mooc-ans/work/dohomeworknew' in path


def _click_submit_confirmation_if_present(driver):
    return driver.execute_script(
        """
        const isVisible = (node) => {
            if (!node) {
                return false;
            }
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return (
                style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0'
                && rect.width > 0
                && rect.height > 0
            );
        };

        const clickNode = (node) => {
            if (!node) {
                return false;
            }
            try {
                node.click();
                return true;
            } catch (error) {
                try {
                    node.dispatchEvent(new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                    }));
                    return true;
                } catch (dispatchError) {
                    return false;
                }
            }
        };

        const getText = (node) => {
            if (!node) {
                return '';
            }
            return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
        };

        const workPop = document.getElementById('workpop');
        if (isVisible(workPop)) {
            const popOk = document.getElementById('popok');
            return {
                action: clickNode(popOk) ? 'workPopOk' : 'workPopVisible',
                dialog_id: 'workpop',
                dialog_text: getText(document.getElementById('popcontent') || workPop),
                primary_text: getText(popOk),
            };
        }

        const verifyDialog = document.getElementById('workVerify');
        if (isVisible(verifyDialog)) {
            return {
                action: 'captcha_required',
                dialog_id: 'workVerify',
                dialog_text: getText(verifyDialog),
                primary_text: '',
            };
        }

        const verifyCodeWin = document.getElementById('verifyCodeWin');
        if (isVisible(verifyCodeWin)) {
            return {
                action: 'captcha_required',
                dialog_id: 'verifyCodeWin',
                dialog_text: getText(verifyCodeWin),
                primary_text: '',
            };
        }

        const submitBack = document.getElementById('submitBack');
        if (isVisible(submitBack)) {
            return {
                action: 'submit_back_blocked',
                dialog_id: 'submitBack',
                dialog_text: getText(submitBack),
                primary_text: getText(document.getElementById('submitBackOk')),
            };
        }

        const confirmDialog = document.getElementById('confirmSubWin');
        if (isVisible(confirmDialog)) {
            const okButton = confirmDialog.querySelector('.bluebtn, .bluebtn_1, .btnBlue, a.bluebtn, button.bluebtn');
            return {
                action: clickNode(okButton) ? 'confirmSubWinOk' : 'confirmSubWinVisible',
                dialog_id: 'confirmSubWin',
                dialog_text: getText(confirmDialog),
                primary_text: getText(okButton),
            };
        }

        const focusDialog = document.getElementById('foucsSubmit') || document.getElementById('foucsSubmit1');
        if (isVisible(focusDialog)) {
            const okButton = focusDialog.querySelector('.bluebtn, .bluebtn_1, .btnBlue, a.bluebtn, button.bluebtn');
            return {
                action: clickNode(okButton) ? 'focusSubmitOk' : 'focusSubmitVisible',
                dialog_id: focusDialog.id || 'focusSubmit',
                dialog_text: getText(focusDialog),
                primary_text: getText(okButton),
            };
        }

        const verifyTip = document.getElementById('verifyTip');
        if (isVisible(verifyTip)) {
            const okButton = verifyTip.querySelector('.bluebtn, .bluebtn_1, .btnBlue, a.bluebtn, button.bluebtn');
            return {
                action: clickNode(okButton) ? 'verifyTipOk' : 'verifyTipVisible',
                dialog_id: 'verifyTip',
                dialog_text: getText(verifyTip),
                primary_text: getText(okButton),
            };
        }

        return {
            action: '',
            dialog_id: '',
            dialog_text: '',
            primary_text: '',
        };
        """
    ) or {'action': '', 'dialog_id': '', 'dialog_text': '', 'primary_text': ''}


def _submit_current_work_page(driver, notify=None, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    submitted = False
    try:
        submitted = bool(driver.execute_script(
            "if (typeof btnBlueSubmit === 'function') { btnBlueSubmit(); return true; } return false;"
        ))
    except Exception:
        submitted = False

    if not submitted:
        selectors = [
            (By.CSS_SELECTOR, '.btnSubmit'),
            (By.CSS_SELECTOR, '.workBtnIndex.btnSubmit'),
            (By.XPATH, "//a[contains(@class, 'btnSubmit')]"),
            (By.XPATH, "//button[contains(., '提交')]"),
            (By.XPATH, "//a[contains(., '提交')]"),
        ]
        for by, value in selectors:
            elements = driver.find_elements(by, value)
            if not elements:
                continue
            element = elements[0]
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                element.click()
            except Exception:
                driver.execute_script('arguments[0].click();', element)
            submitted = True
            break

    if not submitted:
        raise RuntimeError('未找到可提交的章节测验按钮。')

    deadline = time.time() + 20
    last_state = {'action': '', 'dialog_id': '', 'dialog_text': '', 'primary_text': ''}
    while time.time() < deadline:
        _raise_if_parallel_stopped(parallel_controller)
        current_url = str(driver.current_url or '').strip()
        if current_url and not _is_work_answer_page_url(current_url):
            emit_status(notify, 'success', '章节测验已自动提交。')
            return True

        if _safe_accept_alert(driver, timeout=0.6):
            last_state = {'action': 'alertAccepted', 'dialog_id': 'alert', 'dialog_text': '', 'primary_text': ''}
            continue

        state = _click_submit_confirmation_if_present(driver)
        if not isinstance(state, dict):
            state = {'action': str(state or ''), 'dialog_id': '', 'dialog_text': '', 'primary_text': ''}
        action = str(state.get('action') or '')
        if action:
            last_state = state
            if action == 'captcha_required':
                raise RuntimeError('提交时出现验证码校验，暂时无法自动提交，请人工完成。')
            if action == 'submit_back_blocked':
                dialog_text = _normalize_text(state.get('dialog_text')) or '未达到及格线，请重做'
                raise RuntimeError(f'章节测验未能自动提交：{dialog_text}')
            _sleep_with_parallel_stop(0.6, parallel_controller=parallel_controller)
            continue

        _sleep_with_parallel_stop(0.5, parallel_controller=parallel_controller)

    current_url = str(driver.current_url or '').strip()
    if current_url and not _is_work_answer_page_url(current_url):
        emit_status(notify, 'success', '章节测验已自动提交。')
        return True

    dialog_text = _normalize_text(last_state.get('dialog_text'))
    if dialog_text:
        raise RuntimeError(f'章节测验提交后仍停留在答题页：{dialog_text}')
    raise RuntimeError('章节测验提交后仍停留在答题页，未检测到最终跳转。')


def _solve_and_fill_current_driver(driver, cookie, api_key, ai_mode, notify=None, auto_submit=False, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    _wait_for_question_page(driver)
    _raise_if_parallel_stopped(parallel_controller)
    result_payload = solve_homework_page_html(
        page_html=driver.page_source,
        address=driver.current_url,
        cookie=cookie,
        api_key=api_key,
        ai_mode=ai_mode,
        notify=notify,
    )

    structured_answer = result_payload.get('structured_answer')
    if not structured_answer:
        raise RuntimeError(result_payload.get('structured_error') or '结构化答案解析失败，无法自动填写。')

    report = autofill_current_page(driver, structured_answer, notify=notify)
    if auto_submit:
        _submit_current_work_page(driver, notify=notify, parallel_controller=parallel_controller)
    return result_payload, report


def _solve_chapter_quiz(driver, target, card_info, cookie, api_key, ai_mode, notify=None, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    task_url = _normalize_text(card_info.get('task_url'))
    if not task_url:
        raise RuntimeError('未能提取章节测验地址。')

    chapter_handle = driver.current_window_handle
    quiz_handle = _open_new_tab(driver)
    driver.switch_to.window(quiz_handle)
    try:
        _open_authenticated_address(driver, task_url, cookie, notify=notify)
        result_payload, report = _solve_and_fill_current_driver(
            driver,
            cookie=cookie,
            api_key=api_key,
            ai_mode=ai_mode,
            notify=notify,
            auto_submit=True,
            parallel_controller=parallel_controller,
        )
        emit_status(
            notify,
            'success',
            (
                f'章节测验完成：{card_info.get("title") or target.title} '
                f'(成功 {len(report["success"])} / 失败 {len(report["failure"])} / 跳过 {len(report["skipped"])})'
            ),
        )
        return result_payload, report
    finally:
        try:
            driver.close()
        except Exception:
            pass
        _raise_if_parallel_stopped(parallel_controller)
        driver.switch_to.window(chapter_handle)
        driver.refresh()
        try:
            wait_for_page_ready(driver, timeout=PAGE_READY_TIMEOUT)
        except TimeoutException:
            pass


def _run_chapter_target(driver, target, cookie, api_key, ai_mode, notify=None, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    _open_authenticated_address(driver, target.address, cookie, notify=notify)
    handled_count = 0
    max_rounds = max(6, (target.pending_count or 1) * 4)
    last_completion_note = ''

    for _round in range(max_rounds):
        _raise_if_parallel_stopped(parallel_controller)
        total_cards = _get_chapter_card_count(driver)
        if total_cards <= 0:
            raise RuntimeError('未找到章节任务点列表。')

        progress_made = False
        for index in range(1, total_cards + 1):
            _raise_if_parallel_stopped(parallel_controller)
            _load_chapter_card(driver, target, index, total_cards, parallel_controller=parallel_controller)
            card_info = _detect_current_card_task(driver)
            if not card_info.get('unfinished'):
                continue

            card_title = card_info.get('title') or f'任务点 {index}'
            emit_status(notify, 'info', f'正在处理章节任务点：{card_title}')
            if card_info.get('kind') == 'video':
                completion_reason = _play_video_card(
                    driver,
                    target,
                    card_info,
                    notify=notify,
                    parallel_controller=parallel_controller,
                )
                if completion_reason:
                    last_completion_note = f'{card_title}：{completion_reason}'
            elif card_info.get('kind') == 'document':
                _raise_document_manual_review(card_info, target)
            elif card_info.get('kind') == 'quiz':
                _solve_chapter_quiz(
                    driver,
                    target,
                    card_info,
                    cookie=cookie,
                    api_key=api_key,
                    ai_mode=ai_mode,
                    notify=notify,
                    parallel_controller=parallel_controller,
                )
            else:
                raise RuntimeError(f'存在未支持的章节任务点类型：{card_title}')

            handled_count += 1
            progress_made = True
            _raise_if_parallel_stopped(parallel_controller)
            driver.switch_to.default_content()
            driver.refresh()
            try:
                wait_for_page_ready(driver, timeout=PAGE_READY_TIMEOUT)
            except TimeoutException:
                pass
            break

        pending_count = _get_chapter_pending_count(driver, target.knowledge_id)
        unfinished = _current_card_has_pending_job(driver)
        if pending_count <= 0 and not unfinished:
            detail = f'章节已完成，累计处理 {handled_count} 个任务点。'
            if last_completion_note:
                detail += f' 最近完成依据：{last_completion_note}'
            return detail
        if not progress_made and not unfinished:
            detail = '章节已无待完成任务点。'
            if last_completion_note:
                detail += f' 最近完成依据：{last_completion_note}'
            return detail
        if not progress_made:
            raise RuntimeError('章节仍有待完成任务点，但未识别出可自动处理的内容。')

    raise RuntimeError('章节任务未在预期轮次内完成。')


def _run_work_like_target(driver, target, cookie, api_key, ai_mode, notify=None, parallel_controller=None):
    _raise_if_parallel_stopped(parallel_controller)
    _open_authenticated_address(driver, target.address, cookie, notify=notify)
    auto_submit = str(getattr(target, 'submit_policy', 'manual') or 'manual').strip().lower() == 'auto_submit'
    result_payload, report = _solve_and_fill_current_driver(
        driver,
        cookie=cookie,
        api_key=api_key,
        ai_mode=ai_mode,
        notify=notify,
        auto_submit=auto_submit,
        parallel_controller=parallel_controller,
    )
    success_count = len(report.get('success', []))
    failure_count = len(report.get('failure', []))
    skipped_count = len(report.get('skipped', []))
    if auto_submit:
        detail = (
            f'已自动填写并自动提交，成功 {success_count} 题，失败 {failure_count} 题，跳过 {skipped_count} 题。'
        )
    else:
        detail = (
            f'已自动填写，成功 {success_count} 题，失败 {failure_count} 题，跳过 {skipped_count} 题。'
            ' 浏览器保留在最终页面，等待人工复核与提交。'
        )
    return result_payload, report, detail


def _run_single_target_attempt(target, cookie, api_key, ai_mode, browser_type, notify=None, parallel_controller=None):
    normalized_target = _coerce_task_target(target)
    normalized_browser = normalize_browser_type(browser_type)
    session = BrowserSession(normalized_browser)
    keep_open = False
    raw_result = ''
    answer_count = 0
    detail = ''
    session.create_driver()
    if parallel_controller is not None:
        parallel_controller.register_session(session)
    driver = session.driver

    try:
        _raise_if_parallel_stopped(parallel_controller)
        if normalized_target.task_type == 'chapter':
            detail = _run_chapter_target(
                driver,
                normalized_target,
                cookie=cookie,
                api_key=api_key,
                ai_mode=ai_mode,
                notify=notify,
                parallel_controller=parallel_controller,
            )
            return TaskRunResult(
                task_id=normalized_target.task_id,
                task_type=normalized_target.task_type,
                course_name=normalized_target.course_name,
                title=normalized_target.title,
                status='completed',
                retries=0,
                kept_open=False,
                detail=detail,
                address=normalized_target.address,
                browser_type=normalized_browser,
                answer_count=0,
                raw_result='',
            )
        result_payload, _report, detail = _run_work_like_target(
            driver,
            normalized_target,
            cookie=cookie,
            api_key=api_key,
            ai_mode=ai_mode,
            notify=notify,
            parallel_controller=parallel_controller,
        )
        raw_result = result_payload.get('raw_result', '')
        answer_count = len((result_payload.get('structured_answer') or {}).get('answers', []))
        keep_open = True
        return TaskRunResult(
            task_id=normalized_target.task_id,
            task_type=normalized_target.task_type,
            course_name=normalized_target.course_name,
            title=normalized_target.title,
            status='manual_review',
            retries=0,
            kept_open=True,
            detail=detail,
            address=normalized_target.address,
            browser_type=normalized_browser,
            answer_count=answer_count,
            raw_result=raw_result,
        )
    except ManualReviewRequired as exc:
        return TaskRunResult(
            task_id=normalized_target.task_id,
            task_type=normalized_target.task_type,
            course_name=normalized_target.course_name,
            title=normalized_target.title,
            status='manual_review',
            retries=0,
            kept_open=False,
            detail=str(exc),
            address=normalized_target.address,
            browser_type=normalized_browser,
            answer_count=0,
            raw_result='',
        )
    except UnexpectedAlertPresentException as exc:
        _dismiss_runtime_alerts(driver, attempts=4, timeout=0.4)
        raise RuntimeError(f'页面出现拦截性弹窗：{exc}') from exc
    finally:
        if parallel_controller is not None and not keep_open:
            parallel_controller.unregister_session(session)
        if driver is not None and not keep_open:
            try:
                driver.quit()
            except Exception:
                pass


def _run_target_with_retries(target, cookie, api_key, ai_mode, browser_type, notify=None, parallel_controller=None):
    normalized_target = _coerce_task_target(target)
    target_notify = _prefix_notify(
        notify,
        f'{normalized_target.course_name} / {normalized_target.title}: ',
    )
    last_error = None

    if _stop_requested(parallel_controller):
        return _build_stopped_result(normalized_target, browser_type)

    for attempt in range(DEFAULT_PARALLEL_RETRIES + 1):
        try:
            result = _run_single_target_attempt(
                normalized_target,
                cookie=cookie,
                api_key=api_key,
                ai_mode=ai_mode,
                browser_type=browser_type,
                notify=target_notify,
                parallel_controller=parallel_controller,
            )
            result.retries = attempt
            return result
        except ParallelStopRequested as exc:
            return _build_stopped_result(normalized_target, browser_type, detail=str(exc))
        except Exception as exc:
            last_error = exc
            if _stop_requested(parallel_controller):
                return _build_stopped_result(normalized_target, browser_type)
            if attempt < DEFAULT_PARALLEL_RETRIES:
                emit_status(
                    target_notify,
                    'warn',
                    f'任务执行失败，准备重试（{attempt + 1}/{DEFAULT_PARALLEL_RETRIES}）：{exc}',
                )
            else:
                emit_status(target_notify, 'error', f'任务执行失败：{exc}')

    if _stop_requested(parallel_controller):
        return _build_stopped_result(normalized_target, browser_type)

    return TaskRunResult(
        task_id=normalized_target.task_id,
        task_type=normalized_target.task_type,
        course_name=normalized_target.course_name,
        title=normalized_target.title,
        status='failed',
        retries=DEFAULT_PARALLEL_RETRIES,
        kept_open=False,
        detail=str(last_error or '未知错误'),
        address=normalized_target.address,
        browser_type=normalize_browser_type(browser_type),
        answer_count=0,
        raw_result='',
    )


def run_parallel_targets(targets, cookie, api_key, ai_mode, browser_type, max_parallel=3, notify=None, event_callback=None, parallel_controller=None):
    normalized_targets = [_coerce_task_target(item) for item in list(targets or [])]
    if not normalized_targets:
        raise ValueError('未选择任何并发任务。')

    cookie_value = str(cookie or '').strip()
    if not cookie_value:
        raise ValueError('Cookie 不能为空。')

    strategy = _resolve_parallel_strategy(normalized_targets, max_parallel)
    regular_limit = strategy['regular_limit']
    focus_limit = strategy['focus_limit']
    worker_limit = strategy['worker_limit']
    parallel_limit_note = strategy['note']
    pending_focus_targets = [target for target in normalized_targets if _is_focus_sensitive_target(target)]
    pending_regular_targets = [target for target in normalized_targets if not _is_focus_sensitive_target(target)]
    running_futures = {}
    results_by_id = {}
    controller = parallel_controller or ParallelRunController()
    running_focus = 0
    running_regular = 0

    if parallel_limit_note:
        emit_status(notify, 'warn', parallel_limit_note)

    for target in normalized_targets:
        _emit_parallel_event(event_callback, {
            'event': 'queued',
            'task': target.to_dict(),
        })

    with ThreadPoolExecutor(max_workers=worker_limit) as executor:
        def submit_target(task):
            nonlocal running_focus, running_regular
            if _stop_requested(controller):
                return False
            _emit_parallel_event(event_callback, {
                'event': 'started',
                'task': task.to_dict(),
            })
            future = executor.submit(
                _run_target_with_retries,
                task,
                cookie_value,
                api_key,
                ai_mode,
                browser_type,
                notify,
                controller,
            )
            running_futures[future] = task
            if _is_focus_sensitive_target(task):
                running_focus += 1
            else:
                running_regular += 1
            return True

        def fill_available_slots():
            nonlocal running_focus, running_regular
            started = False
            while not _stop_requested(controller):
                submitted = False
                if (
                    focus_limit
                    and pending_focus_targets
                    and running_focus < focus_limit
                    and len(running_futures) < worker_limit
                ):
                    submit_target(pending_focus_targets.pop(0))
                    submitted = True
                    started = True
                while (
                    pending_regular_targets
                    and running_regular < regular_limit
                    and len(running_futures) < worker_limit
                ):
                    submit_target(pending_regular_targets.pop(0))
                    submitted = True
                    started = True
                if not submitted:
                    break
            return started

        fill_available_slots()

        while running_futures:
            done, _ = wait(list(running_futures.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                task = running_futures.pop(future)
                if _is_focus_sensitive_target(task):
                    running_focus = max(0, running_focus - 1)
                else:
                    running_regular = max(0, running_regular - 1)
                try:
                    result = future.result()
                except Exception as exc:
                    result = TaskRunResult(
                        task_id=task.task_id,
                        task_type=task.task_type,
                        course_name=task.course_name,
                        title=task.title,
                        status='failed',
                        retries=DEFAULT_PARALLEL_RETRIES,
                        kept_open=False,
                        detail=str(exc),
                        address=task.address,
                        browser_type=normalize_browser_type(browser_type),
                        answer_count=0,
                        raw_result='',
                    )
                results_by_id[task.task_id] = result
                _emit_parallel_event(event_callback, {
                    'event': 'finished',
                    'task': task.to_dict(),
                    'result': result.to_dict(),
                })
                fill_available_slots()

        remaining_targets = pending_focus_targets + pending_regular_targets
        if remaining_targets:
            for task in remaining_targets:
                result = _build_stopped_result(task, browser_type)
                results_by_id[task.task_id] = result
                _emit_parallel_event(event_callback, {
                    'event': 'finished',
                    'task': task.to_dict(),
                    'result': result.to_dict(),
                })

    ordered_results = [
        results_by_id[target.task_id]
        for target in normalized_targets
        if target.task_id in results_by_id
    ]
    if _stop_requested(controller):
        emit_status(notify, 'warn', f'并发任务已停止，共归档 {len(ordered_results)} 项。')
    else:
        emit_status(notify, 'success', f'并发任务执行完成，共处理 {len(ordered_results)} 项。')
    return ordered_results


def parse_cookie_string(cookie_string):
    raw_value = str(cookie_string or '').strip()
    if not raw_value:
        return []

    if raw_value[:1] in {'{', '['}:
        try:
            parsed = json.loads(raw_value)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            parsed = parsed.get('cookies', [])
        if isinstance(parsed, list):
            cookies = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or '').strip()
                value = str(item.get('value') or '').strip()
                if not name:
                    continue
                cookie = {'name': name, 'value': value}
                for key in ('domain', 'path', 'secure', 'httpOnly', 'expiry', 'sameSite'):
                    if key in item and item.get(key) not in (None, ''):
                        cookie[key] = item.get(key)
                cookies.append(cookie)
            if cookies:
                return cookies

    cookies = []
    for item in raw_value.split(';'):
        piece = item.strip()
        if not piece or '=' not in piece:
            continue
        name, value = piece.split('=', 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies.append({'name': name, 'value': value})
    return cookies


def get_cookie_header_string(cookie_string):
    raw_value = str(cookie_string or '').strip()
    if not raw_value:
        return ''

    if raw_value[:1] in {'{', '['}:
        cookies = parse_cookie_string(raw_value)
        if cookies:
            return '; '.join(
                f"{cookie.get('name', '').strip()}={cookie.get('value', '')}"
                for cookie in cookies
                if str(cookie.get('name', '')).strip()
            ) + ';'
    return raw_value


def _guess_cookie_domain(hostname):
    host = str(hostname or '').strip().lower()
    if not host:
        return ''
    if host.endswith('chaoxing.com'):
        return '.chaoxing.com'
    return host


def _normalize_same_site(value):
    lowered = str(value or '').strip().lower()
    if lowered == 'strict':
        return 'Strict'
    if lowered == 'none':
        return 'None'
    if lowered == 'lax':
        return 'Lax'
    return ''


def _build_browser_cookie(cookie, hostname, default_secure=True):
    payload = {
        'name': str(cookie.get('name') or '').strip(),
        'value': str(cookie.get('value') or ''),
    }
    if not payload['name']:
        return {}

    domain = str(cookie.get('domain') or '').strip() or _guess_cookie_domain(hostname)
    path = str(cookie.get('path') or '').strip() or '/'
    if domain:
        payload['domain'] = domain
    if path:
        payload['path'] = path

    secure_value = cookie.get('secure')
    if secure_value in (True, False):
        payload['secure'] = secure_value
    else:
        payload['secure'] = bool(default_secure)

    if cookie.get('httpOnly') in (True, False):
        payload['httpOnly'] = cookie.get('httpOnly')

    expiry_value = cookie.get('expiry')
    if expiry_value not in (None, ''):
        try:
            payload['expiry'] = int(float(expiry_value))
        except Exception:
            pass

    same_site = _normalize_same_site(cookie.get('sameSite'))
    if same_site:
        payload['sameSite'] = same_site

    return payload


def _inject_cookies_via_cdp(driver, address, cookies):
    parsed_address = urlparse(address)
    hostname = parsed_address.hostname or ''
    default_secure = (parsed_address.scheme or 'https').lower() == 'https'
    inserted = 0

    driver.execute_cdp_cmd('Network.enable', {})
    for cookie in cookies:
        payload = _build_browser_cookie(cookie, hostname, default_secure=default_secure)
        if not payload:
            continue
        try:
            result = driver.execute_cdp_cmd('Network.setCookie', payload)
            if result.get('success'):
                inserted += 1
        except Exception:
            continue
    return inserted


def _inject_cookies_via_webdriver(driver, address, cookies):
    parsed_address = urlparse(address)
    hostname = parsed_address.hostname or ''
    seed_url = f"{parsed_address.scheme or 'https'}://{parsed_address.netloc or hostname}/favicon.ico"
    inserted = 0

    driver.get(seed_url)
    for cookie in cookies:
        payload = _build_browser_cookie(cookie, hostname, default_secure=seed_url.startswith('https://'))
        if not payload:
            continue
        try:
            driver.add_cookie(payload)
            inserted += 1
        except Exception:
            continue
    return inserted


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

    inserted = 0
    if hasattr(driver, 'execute_cdp_cmd'):
        try:
            inserted = _inject_cookies_via_cdp(driver, address, cookies)
        except Exception:
            inserted = 0

    if inserted <= 0:
        inserted = _inject_cookies_via_webdriver(driver, address, cookies)

    if inserted <= 0:
        raise RuntimeError('浏览器未能写入任何 Cookie，请重新登录获取 Cookie。')

    driver.get(address)
    wait_for_page_ready(driver)


def get_hidden_answer_value(driver, qid):
    return driver.execute_script(
        "var el = document.getElementById(arguments[0]); return el ? (el.value || '') : '';",
        f'answer{qid}',
    )


def find_question_element(driver, qid, timeout=12):
    return WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script(
            """
            const qid = String(arguments[0] || '');
            const direct = document.getElementById(`question${qid}`);
            if (direct) {
                return direct;
            }

            const chapterBlock = document.querySelector(`div.singleQuesId[data="${qid}"]`);
            if (chapterBlock) {
                return chapterBlock;
            }

            const answerField = document.getElementById(`answer${qid}`) || document.querySelector(`[name="answer${qid}"]`);
            if (answerField) {
                return answerField.closest('.singleQuesId, .TiMu') || answerField;
            }

            const blankField = document.getElementById(`answerEditor${qid}1`) || document.querySelector(`[name="answerEditor${qid}1"]`);
            if (blankField) {
                return blankField.closest('.singleQuesId, .TiMu') || blankField;
            }

            return null;
            """,
            str(qid or ''),
        )
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
    question_el = find_question_element(driver, qid, timeout=12)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    option_elements = question_el.find_elements(By.CSS_SELECTOR, "div[onclick*='addChoice'], li[onclick*='addChoice']")
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
    question_el = find_question_element(driver, qid, timeout=12)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", question_el)

    option_elements = question_el.find_elements(By.CSS_SELECTOR, "div[onclick*='addMultipleChoice'], li[onclick*='addMultipleChoice']")
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
    question_el = find_question_element(driver, qid, timeout=12)
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
    question_el = find_question_element(driver, qid, timeout=12)
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


def autofill_current_page(driver, structured_answer, notify=None):
    if not isinstance(structured_answer, dict) or not structured_answer.get('answers'):
        raise ValueError('缺少可自动填写的结构化答案。')

    report = {'success': [], 'failure': [], 'skipped': []}
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
    return report


def autofill_homework(address, cookie, structured_answer, browser_type, notify=None):
    session = BrowserSession(browser_type)
    session.create_driver()
    driver = session.driver

    emit_status(notify, 'progress', '正在打开作业页并注入 Cookie...')
    inject_cookies_and_open(driver, address, cookie)

    current_url = driver.current_url.lower()
    if any(token in current_url for token in ('login', 'passport', 'cas', 'verify')):
        raise RuntimeError('页面仍然跳转到登录页，Cookie 可能已失效。')

    report = autofill_current_page(driver, structured_answer, notify=notify)
    auto_submit = is_chapter_quiz_address(driver.current_url)
    if auto_submit:
        _submit_current_work_page(driver, notify=notify, parallel_controller=None)
    report['auto_submitted'] = auto_submit
    report['browser_kept_open'] = True
    return report


def print_autofill_report(report):
    success_count = len(report.get('success', []))
    failure_count = len(report.get('failure', []))
    skipped_count = len(report.get('skipped', []))
    failed_numbers = [str(item.get('question_no') or item.get('qid')) for item in report.get('failure', [])]
    auto_submitted = bool(report.get('auto_submitted'))

    notes = [f"失败题号: {', '.join(failed_numbers)}" if failed_numbers else '失败题号: 无']
    ui_summary('自动填写结果', [
        ('成功题数', success_count),
        ('失败题数', failure_count),
        ('跳过题数', skipped_count),
    ], notes=notes)
    if auto_submitted:
        ui_status('success', '当前页面识别为章节测验，程序已在填写完成后自动提交。')
    else:
        ui_status('info', '浏览器已保留在作业页，程序不会自动提交，请先人工检查后再决定是否提交。')


def run_autofill(address, cookie, structured_answer, browser_type, notify=None):
    normalized_browser = normalize_browser_type(browser_type)
    if not isinstance(structured_answer, dict) or not structured_answer.get('answers'):
        raise ValueError('缺少可自动填写的结构化答案。')

    report = autofill_homework(
        str(address or '').lstrip('\ufeff').strip(),
        str(cookie or '').strip(),
        structured_answer,
        normalized_browser,
        notify=notify,
    )
    emit_status(notify, 'success', '自动填写流程已结束。')
    return report


def solve_homework(address, cookie, api_key, ai_mode, notify=None, browser_type=None):
    address_value = str(address or '').lstrip('\ufeff').strip()
    cookie_value = str(cookie or '').strip()
    api_key_value = str(api_key or '').strip()

    if not address_value:
        raise ValueError('作业地址不能为空。')
    if not cookie_value:
        raise ValueError('Cookie 不能为空。')
    if not api_key_value:
        raise ValueError('API 密钥不能为空。')

    emit_status(notify, 'progress', '正在获取作业页面...')
    try:
        page_html = fetch_homework_page(
            address_value,
            cookie_value,
            browser_type=browser_type,
            notify=notify,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f'网络请求失败: {exc}') from exc
    return solve_homework_page_html(
        page_html=page_html,
        address=address_value,
        cookie=cookie_value,
        api_key=api_key_value,
        ai_mode=ai_mode,
        notify=notify,
    )


def answer():
    """获取作业内容并使用 AI 解答"""
    ui_title('作业解答助手')

    cookie_value = cookie_store.get_or_prompt()
    address_value = address_store.get_or_prompt().lstrip('\ufeff').strip()

    mode_choice = ''
    while mode_choice not in ('1', '2'):
        mode_choice = input(ui_prompt('请选择 AI 模式 (1=标准/2=深度思考): ')).strip()

    api_key = load_api_key()

    try:
        result_payload = solve_homework(
            address_value,
            cookie_value,
            api_key,
            mode_choice,
            notify=ui_status,
            browser_type=DEFAULT_BROWSER,
        )
    except Exception as e:
        ui_status('error', str(e))
        return ''

    summary = result_payload['question_summary']
    ui_summary('题目提取结果', [
        ('题目数量', summary['count']),
        ('题型覆盖', summary['type_summary']),
    ])

    ui_section('AI 解答结果')
    ui_block(result_payload['raw_result'])

    structured_answer = result_payload['structured_answer']
    if structured_answer and ask_yes_no('是否自动填写到网页'):
        browser_type = choose_browser()
        try:
            report = run_autofill(
                address_value,
                cookie_value,
                structured_answer,
                browser_type,
                notify=ui_status,
            )
            print_autofill_report(report)
        except Exception as autofill_error:
            ui_status('error', f'自动填写失败: {autofill_error}')

    open_qa_loop(result_payload['qa_context'])
    return result_payload['raw_result']


def _parse_multi_select_indices(raw_value, max_index):
    text = str(raw_value or '').strip().lower()
    if not text:
        raise ValueError('请输入至少一个编号。')
    if text in {'all', 'a', '*'}:
        return list(range(1, max_index + 1))

    indices = set()
    for token in re.split(r'[\s,，]+', text):
        if not token:
            continue
        if '-' in token:
            start_text, end_text = token.split('-', 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                start, end = end, start
            for value in range(start, end + 1):
                indices.add(value)
        else:
            indices.add(int(token))

    invalid = [value for value in indices if value < 1 or value > max_index]
    if invalid:
        raise ValueError(f'存在超出范围的编号: {invalid}')
    return sorted(indices)


def _prompt_multi_select(items, title, formatter):
    if not items:
        return []

    ui_section(title)
    for index, item in enumerate(items, start=1):
        print(f'{index}. {formatter(item)}')

    while True:
        raw_value = input(ui_prompt('请输入编号或范围（示例: 1 3-5，输入 all 选择全部）: ')).strip()
        try:
            indices = _parse_multi_select_indices(raw_value, len(items))
            return [items[index - 1] for index in indices]
        except Exception as exc:
            ui_status('warn', f'选择格式有误：{exc}')


def _task_type_label(task_type):
    mapping = {
        'chapter': '章节',
        'homework': '作业',
        'exam': '考试',
    }
    return mapping.get(task_type, task_type)


def _print_parallel_results(results):
    completed = [item for item in results if item.status == 'completed']
    stopped = [item for item in results if item.status == 'stopped']
    manual_review = [item for item in results if item.status == 'manual_review']
    failed = [item for item in results if item.status == 'failed']
    ui_summary('并发执行结果', [
        ('总任务数', len(results)),
        ('已完成', len(completed)),
        ('已停止', len(stopped)),
        ('待人工提交', len(manual_review)),
        ('失败', len(failed)),
    ])

    for result in results:
        status_text = {
            'completed': '已完成',
            'stopped': '已停止',
            'manual_review': '待人工提交',
            'failed': '失败',
        }.get(result.status, result.status)
        ui_status(
            'info' if result.status not in {'failed'} else 'error',
            f"[{status_text}] {_task_type_label(result.task_type)} | {result.course_name} | {result.title} | {result.detail}",
        )


def course_center():
    ui_title('课程中心 / 多任务并发')
    cookie_value = cookie_store.get_or_prompt()
    browser_type = choose_browser()

    try:
        courses = load_course_catalog(cookie_value, browser_type, notify=ui_status)
    except Exception as exc:
        ui_status('error', f'课程列表载入失败: {exc}')
        return []

    if not courses:
        ui_status('warn', '未发现任何课程。')
        return []

    selected_courses = _prompt_multi_select(
        courses,
        '课程列表',
        lambda course: f"{course.course_name} | {course.progress_text or '无进度信息'}",
    )
    if not selected_courses:
        ui_status('warn', '未选择任何课程。')
        return []

    all_targets = []
    for course in selected_courses:
        try:
            catalog = load_course_task_catalog(course.course_url, cookie_value, browser_type, notify=ui_status)
        except Exception as exc:
            ui_status('warn', f'{course.course_name} 任务目录载入失败: {exc}')
            continue
        all_targets.extend(catalog.get('chapters', []))
        all_targets.extend(catalog.get('homework', []))
        all_targets.extend(catalog.get('exams', []))

    if not all_targets:
        ui_status('warn', '所选课程中没有可执行的章节、作业或考试。')
        return []

    selected_targets = _prompt_multi_select(
        all_targets,
        '任务列表',
        lambda task: (
            f"[{_task_type_label(task.task_type)}] {task.course_name} | {task.title}"
            + (f" | 待完成 {task.pending_count}" if task.task_type == 'chapter' and task.pending_count else '')
            + (f" | {task.status_text}" if task.status_text else '')
        ),
    )
    if not selected_targets:
        ui_status('warn', '未选择任何任务。')
        return []

    mode_choice = ''
    while mode_choice not in ('1', '2'):
        mode_choice = input(ui_prompt('请选择 AI 模式 (1=标准/2=深度思考): ')).strip()
    api_key = load_api_key()

    state = {
        'queued': set(),
        'running': set(),
        'completed': set(),
        'stopped': set(),
        'failed': set(),
        'manual_review': set(),
    }

    def event_callback(payload):
        event_name = payload.get('event')
        task_info = payload.get('task') or {}
        task_id = task_info.get('task_id', '')
        if not task_id:
            return

        if event_name == 'queued':
            state['queued'].add(task_id)
        elif event_name == 'started':
            state['queued'].discard(task_id)
            state['running'].add(task_id)
        elif event_name == 'finished':
            state['queued'].discard(task_id)
            state['running'].discard(task_id)
            result_info = payload.get('result') or {}
            status = result_info.get('status', '')
            if status == 'completed':
                state['completed'].add(task_id)
            elif status == 'stopped':
                state['stopped'].add(task_id)
            elif status == 'manual_review':
                state['manual_review'].add(task_id)
            else:
                state['failed'].add(task_id)

        ui_status(
            'info',
            (
                f"并发状态：待启动 {len(state['queued'])} | 进行中 {len(state['running'])} "
                f"| 已完成 {len(state['completed'])} | 已停止 {len(state['stopped'])} | 失败 {len(state['failed'])} "
                f"| 待人工提交 {len(state['manual_review'])}"
            ),
        )

    try:
        results = run_parallel_targets(
            targets=selected_targets,
            cookie=cookie_value,
            api_key=api_key,
            ai_mode=mode_choice,
            browser_type=browser_type,
            max_parallel=DEFAULT_PARALLEL_LIMIT,
            notify=ui_status,
            event_callback=event_callback,
        )
    except Exception as exc:
        ui_status('error', f'并发执行失败: {exc}')
        return []

    _print_parallel_results(results)
    return results


def main():
    ui_title('超星学习通自动作业助手 v3.0.2', icon='🤖')

    print_browser_driver_status()
    while True:
        ui_menu('主菜单', [
            '1. 自动获取 Cookie 并登录',
            '2. 开始作业解答',
            '3. 修改配置 (地址/Cookie/API)',
            '4. 重新检测浏览器驱动',
            '5. 课程中心 / 多任务并发',
            '0. 退出程序',
        ])

        choice = input(ui_prompt('请选择 (0-5): ')).strip()
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
        elif choice == '5':
            try:
                course_center()
            except KeyboardInterrupt:
                ui_status('warn', '用户中断课程中心流程。')
            except Exception as e:
                ui_status('error', f'课程中心流程出错: {e}')
        elif choice == '0':
            break
        else:
            ui_status('warn', '无效选择，请输入 0-5。')

    ui_title('程序已完成')


if __name__ == '__main__':
    main()
