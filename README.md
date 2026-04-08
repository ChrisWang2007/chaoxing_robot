# 超星学习通自动作业助手

`v3.0.2` 是当前仓库的最新发布版本。项目提供源码运行、桌面 EXE 打包，以及适合 GitHub Release 分发的便携压缩包。

## 项目简介

这是一个面向超星学习通页面的本地自动化工具，当前版本支持：

- 自动登录并获取 Cookie
- 结构化抓取课程、章节、作业、考试等任务
- 调用 DeepSeek API 生成答案
- 自动填写单选、多选、判断、填空、论述题
- 章节测验填写完成后自动提交
- 普通作业填写完成后保留页面供人工复核，不默认自动提交
- 提供 GUI 工作台与 CLI 入口
- 支持桌面交付目录和 GitHub Release 便携包

## v3.0.2 重点改进

- 修复章节测验页自动填写后未继续执行自动提交的问题
- 新增章节测验地址识别逻辑，仅对章节测验页启用自动提交
- 普通作业页继续保持手动提交，不改变原有安全策略
- 兼容章节测验提交时的页内确认弹窗流程
- GUI 与 CLI 的自动填写提示已区分“章节测验自动提交”和“普通作业人工提交”

## 运行环境

- Windows
- Python 3.10+
- 已安装浏览器和对应版本的 WebDriver

建议安装依赖：

```bash
pip install selenium requests beautifulsoup4 openai customtkinter darkdetect pyinstaller
```

## 入口说明

GUI 入口：

```bash
python mooc_robot_gui.py
```

CLI 入口：

```bash
python mooc_robot.py
```

说明：

- `mooc_robot_gui.py` 是当前推荐入口，也是 EXE 打包入口
- `mooc_robot.py` 保留命令行模式，适合直接调试或排查

## 本地运行所需文件

程序目录建议保留以下文件：

- `mooc_robot.py`
- `mooc_robot_gui.py`
- `page_address.txt`
- `page_cookie.txt`
- `api.txt`
- `edgeDriver.exe`
- `chromeDriver.exe`
- `firefoxDriver.exe`
- `ieDriverServer.exe`

其中：

- `page_address.txt` 保存作业或课程页面地址
- `page_cookie.txt` 保存登录 Cookie
- `api.txt` 保存 DeepSeek API Key
- 浏览器驱动按需放到程序同目录，程序会自动检测可用状态

## 推荐使用流程

1. 准备可用的浏览器驱动并放到程序目录
2. 启动 `python mooc_robot_gui.py`
3. 在 GUI 中填写或载入地址、Cookie、API Key
4. 先执行登录 / Cookie 获取，再载入课程、章节或作业
5. 生成答案后选择自动填写
6. 普通作业请人工复核后再提交；章节测验会在填写完成后自动提交

## 章节任务说明

`v3.0.2` 起，章节自动化中的章节测验页与普通作业页共享同一套题目提取与自动填写能力，但提交策略不同：

- 兼容章节页专用题干布局
- 兼容章节页专用选项列表结构
- 支持章节测验中的填空题、判断题、多选题、单选题
- 论述题仍沿用普通作业页相同的文本题填写逻辑
- 章节测验：填写完成后自动提交
- 普通作业：填写完成后保留页面，等待人工检查与提交

## GitHub Release 资产

当前发布默认提供以下资产：

- `mooc_robot.exe`
- `mooc_robot_portable.zip`

说明：

- `mooc_robot.exe` 为单文件 GUI 程序
- `mooc_robot_portable.zip` 内包含 `mooc_robot.exe` 和 3 个空白配置文件
- Release 资产不包含任何浏览器驱动
- Release 资产不包含真实本地配置或 Cookie

## 打包方式

执行：

```bash
python package_exe.py
```

或：

```bash
python build.py
```

打包完成后会在桌面生成两个产物：

- `~/Desktop/mooc_robot_release`
- `~/Desktop/mooc_robot_portable.zip`

其中：

- `mooc_robot_release` 为本地交付目录，包含 `mooc_robot.exe`、当前本地配置文件、当前本地驱动文件
- `mooc_robot_portable.zip` 为公开发布便携包，仅包含 `mooc_robot.exe` 和 3 个空白配置文件

## DeepSeek API 配置

当前程序通过 OpenAI SDK 兼容方式调用 DeepSeek：

- `base_url`: `https://api.deepseek.com`
- 模型：
  - `deepseek-chat`
  - `deepseek-reasoner`

示例：

```python
from openai import OpenAI

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)
```

## 浏览器驱动下载

仓库不再直接提交浏览器驱动，请根据本机浏览器版本自行下载：

- Edge WebDriver  
  <https://developer.microsoft.com/microsoft-edge/tools/webdriver/>
- ChromeDriver  
  <https://chromedriver.chromium.org/downloads>
- GeckoDriver / Firefox  
  <https://github.com/mozilla/geckodriver/releases>
- IE Driver Server  
  <https://www.selenium.dev/downloads/>

驱动文件名需与程序默认识别名称保持一致：

- `edgeDriver.exe`
- `chromeDriver.exe`
- `firefoxDriver.exe`
- `ieDriverServer.exe`

## 注意事项

- 不要把真实 `api.txt`、`page_cookie.txt`、`page_address.txt` 上传到公开仓库
- 普通作业自动填写后不会自动提交，请务必人工复核
- 章节测验会在填写完成后自动提交，使用前请确认这是你期望的行为
- 浏览器驱动版本必须与浏览器版本匹配
- Cookie 失效后需要重新登录获取

## 更新记录

详细版本说明见 `CHANGELOG.md`。
