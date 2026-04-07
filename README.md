# 超星学习通自动作业助手

一个面向超星学习通作业页的本地自动化工具，支持：

- 自动获取 Cookie 并登录
- 结构化抓取作业题目
- 调用 DeepSeek API 生成答案
- 按题号自动填写单选、多选、填空、判断、论述题
- 自动填写后保留浏览器供人工检查，不自动提交
- 一键打包为桌面 EXE 交付目录

## 当前版本特性

- 题目抓取已升级为结构化提取，不再只依赖整页文本
- 自动填写已覆盖客观题、填空题、论述题
- AI 输出支持“结构化 JSON 答案块 + 解释说明”
- 终端界面已做轻量卡片化整理
- 主菜单支持手动重新检测浏览器驱动
- 已修复论述题误报填写失败的问题
- 已静默 Chromium 的 SSL handshake 控制台噪音日志
- 打包流程支持外置驱动、外置配置文件

## 运行环境

- Windows
- Python 3.10+
- 已安装浏览器和对应 WebDriver

建议先安装依赖：

```bash
pip install selenium requests beautifulsoup4 openai
```

## 目录说明

运行主程序时，程序目录下建议保留以下文件：

- `mooc_robot.py`
- `page_address.txt`
- `page_cookie.txt`
- `api.txt`
- `edgeDriver.exe`
- `chromeDriver.exe`
- `firefoxDriver.exe`
- `ieDriverServer.exe`

说明：

- `page_address.txt`：保存作业页面地址
- `page_cookie.txt`：保存 Cookie
- `api.txt`：保存 DeepSeek API Key
- 4 个驱动文件按需放同目录即可，程序会自动检测

## 如何使用

启动方式：

源码版：

```bash
python mooc_robot.py
```

Release 版：

- 推荐下载 `mooc_robot_portable.zip`，解压后直接运行 `mooc_robot.exe`
- 也可以单独下载 `mooc_robot.exe`，放到一个独立目录后直接双击运行
- 无论使用哪种 Release 方式，浏览器驱动都需要单独下载并放到 `mooc_robot.exe` 同目录
- 裸 `exe` 首次运行后，程序会在 EXE 同目录读写 `page_address.txt`、`page_cookie.txt`、`api.txt`

主菜单功能：

1. 自动获取 Cookie 并登录
2. 开始作业解答
3. 修改配置（地址 / Cookie / API）
4. 重新检测浏览器驱动
0. 退出程序

推荐使用流程：

1. 准备一个可用的浏览器驱动，放到程序同目录
2. 运行 `python mooc_robot.py`
3. 先使用“自动获取 Cookie 并登录”，把 Cookie 保存到本地
4. 在 `page_address.txt` 中填入作业页面地址
5. 在 `api.txt` 中填入 DeepSeek API Key
6. 选择“开始作业解答”
7. AI 返回答案后，可选择自动填写到网页
8. 程序填写完成后不会自动提交，请手动检查后再决定是否提交

## GitHub Release 使用

当前 GitHub Release 默认提供两个公开资产：

- `mooc_robot.exe`
- `mooc_robot_portable.zip`

说明：

- `mooc_robot_portable.zip` 内包含 `mooc_robot.exe` 和 3 个空白配置文件，适合直接解压后使用
- 单独下载 `mooc_robot.exe` 也可以直接运行，程序会在同目录创建或更新配置文件
- 两种公开资产都不包含浏览器驱动，请根据自己的浏览器版本单独下载驱动并放到 EXE 同目录

## DeepSeek API 创建方法

当前程序通过 OpenAI SDK 兼容方式调用 DeepSeek：

- `base_url`: `https://api.deepseek.com`
- 模型：
  - `deepseek-chat`
  - `deepseek-reasoner`

官方入口：

- DeepSeek 开放平台：<https://platform.deepseek.com/>
- DeepSeek API 文档：<https://api-docs.deepseek.com/>

创建 API Key 的基本步骤：

1. 打开 DeepSeek 开放平台并登录账号
2. 完成平台要求的账号设置
3. 进入 API Key 管理页面
4. 创建新的 API Key
5. 复制生成的 Key
6. 将 Key 写入程序目录下的 `api.txt`

程序中的实际调用方式与官方文档一致，当前代码使用：

```python
from openai import OpenAI

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)
```

## 浏览器驱动说明

本仓库不再直接提供浏览器驱动，请自行下载并放在程序目录。

常见驱动下载入口：

- Edge WebDriver  
  <https://developer.microsoft.com/microsoft-edge/tools/webdriver/>
- ChromeDriver  
  <https://chromedriver.chromium.org/downloads>
- GeckoDriver / Firefox  
  <https://github.com/mozilla/geckodriver/releases>
- IE Driver Server  
  <https://www.selenium.dev/downloads/>

文件名需与程序默认识别一致：

- `edgeDriver.exe`
- `chromeDriver.exe`
- `firefoxDriver.exe`
- `ieDriverServer.exe`

## 自动填写说明

当前自动填写逻辑支持：

- 单选题
- 多选题
- 填空题
- 判断题
- 论述题 / 文本题

自动填写的关键行为：

- 通过 `qid` 定位题目
- 客观题使用页面原生点击逻辑触发答案更新
- 文本题和填空题通过 UEditor / textarea 写入
- 填写完成后输出成功 / 失败 / 跳过统计
- 默认不自动提交

## 打包 EXE

当前项目支持把程序打包为桌面交付目录：

```bash
python package_exe.py
```

或：

```bash
python build.py
```

打包结果会生成到桌面 `mooc_robot_release`，并遵循以下规则：

- `mooc_robot.exe` 为单文件 EXE
- 浏览器驱动外置，不打进 EXE
- `api.txt`、`page_cookie.txt`、`page_address.txt` 外置，不打进 EXE
- GitHub Release 已额外发布不含驱动的便携包，便于公开分发

## 注意事项

- 不要把自己的 `api.txt`、`page_cookie.txt`、`page_address.txt` 上传到公开仓库
- 自动填写只是辅助工具，提交前请务必人工复核
- 浏览器驱动版本应与本机浏览器版本匹配
- 若 Cookie 失效，需要重新登录获取

## 更新记录

详细更新说明见：

- `CHANGELOG.md`
