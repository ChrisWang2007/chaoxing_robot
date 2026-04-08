import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit('缺少 customtkinter，请先执行 pip install customtkinter') from exc

from mooc_robot import (
    BROWSER_LABELS,
    DEFAULT_PARALLEL_LIMIT,
    LoginWaitController,
    ParallelRunController,
    UI_STATUS_PREFIX,
    ask_followup,
    get_driver_status,
    load_course_catalog,
    load_course_task_catalog,
    load_config_values,
    run_parallel_targets,
    run_autofill,
    run_manual_login,
    save_config_values,
    solve_homework,
)


class MoocRobotGUI(ctk.CTk):
    SIDEBAR_WIDTH = 300
    MIN_SIDEBAR_WIDTH = 270
    MAX_SIDEBAR_WIDTH = 420
    MIN_MAIN_WIDTH = 760
    MIN_WINDOW_WIDTH = 1100
    MIN_WINDOW_HEIGHT = 780
    HANDLE_WIDTH = 8

    UI_QUEUE_IDLE_MS = 16
    UI_QUEUE_BUSY_MS = 0
    FRAME_MS = 16
    COLOR_ANIMATION_MS = 100
    BUTTON_PULSE_MS = 120
    WRAP_DELTA = 12
    COMPACT_SIDEBAR_THRESHOLD = 292
    MAIN_ACTION_STACK_THRESHOLD = 1020
    RESULT_STACK_THRESHOLD = 940

    COLORS = {
        'app_bg': '#ECF2F8',
        'sidebar_shell': '#F2F6FB',
        'main_shell': '#FBFCFE',
        'card_bg': '#FFFFFF',
        'panel_bg': '#F5F8FC',
        'panel_alt': '#EEF3F9',
        'border': '#D8E2EE',
        'border_soft': '#E5ECF4',
        'border_active': '#2F6FED',
        'text_primary': '#19324D',
        'text_secondary': '#5E758C',
        'text_muted': '#8FA1B4',
        'brand': '#2F6FED',
        'brand_hover': '#2459BD',
        'brand_soft': '#E7F0FF',
        'success': '#1B9C73',
        'success_soft': '#E8F7F1',
        'warning': '#D48A1A',
        'warning_soft': '#FFF4E3',
        'danger': '#D44D5C',
        'danger_soft': '#FDEBED',
        'splitter': '#D9E4F0',
        'splitter_hover': '#AFC7E9',
        'splitter_active': '#2F6FED',
    }

    BROWSER_SEGMENTS = {
        'Edge': 'edge',
        'Chrome': 'chrome',
        'Firefox': 'firefox',
        'IE': 'ie',
    }
    AI_SEGMENTS = {
        '标准模式': '1',
        '深度思考': '2',
    }
    STAGE_META = {
        'parallel': ('步骤 0', '课程并发中心'),
        'solve': ('步骤 1', '作业解答'),
        'result': ('步骤 2', '结果与自动填写'),
        'qa': ('步骤 3', '问答追问'),
    }

    def __init__(self):
        super().__init__()
        self.title('超星学习通自动作业助手')
        self.geometry('1460x980')
        self.minsize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.configure(fg_color=self.COLORS['app_bg'])

        self.ui_queue = queue.Queue()
        self.ui_pump_after_id = None
        self.layout_after_id = None
        self.busy_tasks = set()
        self.current_login_controller = None
        self.last_solution = None
        self.qa_context = None
        self.active_stage = 'parallel'
        self.section_meta = {}
        self.stage_cards = {}
        self.wrap_labels = []
        self.sidebar_button_groups = []
        self.sidebar_width = self.SIDEBAR_WIDTH
        self.sidebar_max_width = self.MAX_SIDEBAR_WIDTH
        self.sidebar_compact = None
        self.main_actions_stacked = None
        self.qa_actions_stacked = None
        self.result_stacked = None
        self.applied_sidebar_width = None
        self.layout_pass_pending = False
        self.layout_measure_requested = False
        self.scroll_sync_after_id = None
        self.last_root_size = (0, 0)
        self.drag_origin_x = 0
        self.drag_origin_width = self.SIDEBAR_WIDTH
        self.is_sidebar_resizing = False
        self.active_scroller = None
        self.animation_tokens = {}
        self.log_count = 0
        self.last_log_message = ''
        self.ui_ready = False
        self.course_catalog = []
        self.selected_course_urls = set()
        self.task_catalog_by_course = {}
        self.task_targets_by_id = {}
        self.task_checkbox_vars = {}
        self.course_button_meta = {}
        self.parallel_task_states = {}
        self.parallel_results = []
        self.parallel_controllers = []
        self.active_parallel_controller = None
        self.parallel_stop_requested = False

        self.driver_path_var = tk.StringVar(value='')
        self.driver_summary_var = tk.StringVar(value='当前使用程序目录或 EXE 同级目录检测驱动。')
        self.driver_available_var = tk.StringVar(value='可用驱动：无')
        self.driver_missing_var = tk.StringVar(value='缺失驱动：无')
        self.config_summary_var = tk.StringVar(value='地址：未配置\nCookie：未配置\nAPI：未配置')
        self.login_status_var = tk.StringVar(value='等待开始登录。')
        self.question_count_var = tk.StringVar(value='题目数量：-')
        self.question_types_var = tk.StringVar(value='题型覆盖：-')
        self.result_summary_var = tk.StringVar(value='结构化结果：尚未生成')
        self.autofill_summary_var = tk.StringVar(value='自动填写：尚未执行')
        self.course_summary_var = tk.StringVar(value='课程中心：登录并获取 Cookie 后可载入课程。')
        self.task_summary_var = tk.StringVar(value='任务中心：请选择课程后载入章节 / 作业 / 考试。')
        self.parallel_summary_var = tk.StringVar(value='并发运行：等待开始。')
        self.parallel_pending_var = tk.StringVar(value='待启动：0')
        self.parallel_running_var = tk.StringVar(value='进行中：0')
        self.parallel_completed_var = tk.StringVar(value='已完成：0')
        self.parallel_stopped_var = tk.StringVar(value='已停止：0')
        self.parallel_failed_var = tk.StringVar(value='失败：0')
        self.parallel_manual_var = tk.StringVar(value='待人工提交：0')
        self.log_summary_var = tk.StringVar(value='日志已折叠。')
        self.browser_segment_var = tk.StringVar(value='Edge')
        self.ai_segment_var = tk.StringVar(value='标准模式')

        self.protocol('WM_DELETE_WINDOW', self._on_close)

        self._build_ui()
        self._build_final_copy_state()
        self._bind_window_events()
        self._load_config_into_form()
        self._refresh_driver_status(show_log=False)
        self._set_stage_focus('parallel', animate=False)
        self._request_layout_pass('init', measure=True)
        self.after(0, self._run_startup_reveal)
        self._schedule_ui_queue_pump(self.UI_QUEUE_IDLE_MS)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=self.SIDEBAR_WIDTH)
        self.grid_columnconfigure(1, weight=0, minsize=self.HANDLE_WIDTH)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar_shell = ctk.CTkFrame(
            self,
            width=self.SIDEBAR_WIDTH,
            corner_radius=28,
            fg_color=self.COLORS['sidebar_shell'],
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.sidebar_shell.grid(row=0, column=0, sticky='nsew', padx=(18, 0), pady=18)
        self.sidebar_shell.grid_propagate(False)

        self.sidebar_resize_handle = ctk.CTkFrame(
            self,
            width=self.HANDLE_WIDTH,
            corner_radius=999,
            fg_color='transparent',
            cursor='sb_h_double_arrow',
        )
        self.sidebar_resize_handle.grid(row=0, column=1, sticky='ns', padx=6, pady=18)
        self.sidebar_resize_handle.grid_propagate(False)

        self.sidebar_resize_bar = ctk.CTkFrame(
            self.sidebar_resize_handle,
            width=4,
            corner_radius=999,
            fg_color=self.COLORS['splitter'],
            cursor='sb_h_double_arrow',
        )
        self.sidebar_resize_bar.place(relx=0.5, rely=0.5, relheight=0.74, anchor='center')
        self.sidebar_resize_bar._current_fg_color = self.COLORS['splitter']

        self.main_shell = ctk.CTkFrame(
            self,
            corner_radius=30,
            fg_color=self.COLORS['main_shell'],
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.main_shell.grid(row=0, column=2, sticky='nsew', padx=(0, 18), pady=18)

        self.sidebar_scroller = self._build_scroll_canvas(
            self.sidebar_shell,
            bg_color=self.COLORS['sidebar_shell'],
            name='sidebar',
        )
        self.main_scroller = self._build_scroll_canvas(
            self.main_shell,
            bg_color=self.COLORS['main_shell'],
            name='main',
        )
        self.sidebar_scroll = self.sidebar_scroller['content']
        self.main_scroll = self.main_scroller['content']
        self.active_scroller = self.main_scroller

        self._build_sidebar()
        self._build_main_workspace()
        self.ui_ready = True

    def _build_scroll_canvas(self, parent, bg_color, name):
        host = ctk.CTkFrame(parent, fg_color='transparent')
        host.pack(fill='both', expand=True, padx=0, pady=0)
        host.grid_columnconfigure(0, weight=1)
        host.grid_columnconfigure(1, weight=0)
        host.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            host,
            bg=bg_color,
            bd=0,
            highlightthickness=0,
            relief='flat',
        )
        canvas.grid(row=0, column=0, sticky='nsew')

        scrollbar = ctk.CTkScrollbar(
            host,
            orientation='vertical',
            command=canvas.yview,
            fg_color='transparent',
            button_color='#D8E2F0',
            button_hover_color='#C6D5E8',
            width=10,
            corner_radius=999,
        )
        scrollbar.grid(row=0, column=1, sticky='ns', padx=(10, 0))
        canvas.configure(yscrollcommand=scrollbar.set)

        content = ctk.CTkFrame(canvas, fg_color='transparent', corner_radius=0)
        window_id = canvas.create_window((0, 0), window=content, anchor='nw')

        scroller = {
            'name': name,
            'host': host,
            'canvas': canvas,
            'scrollbar': scrollbar,
            'content': content,
            'window_id': window_id,
            'canvas_width': 0,
        }

        canvas.bind(
            '<Configure>',
            lambda event, current=scroller: self._on_scroller_canvas_configure(current, event.width),
            add='+',
        )
        content.bind(
            '<Configure>',
            lambda _event, current=scroller: self._on_scroller_content_configure(current),
            add='+',
        )

        for widget in (host, canvas, content):
            widget.bind('<Enter>', lambda _event, current=scroller: self._set_active_scroller(current), add='+')

        return scroller

    def _build_sidebar(self):
        self.brand_panel = ctk.CTkFrame(
            self.sidebar_scroll,
            fg_color=self.COLORS['brand_soft'],
            corner_radius=22,
            border_width=1,
            border_color='#D7E5FF',
        )
        self.brand_panel.pack(fill='x', pady=(0, 14))

        ctk.CTkLabel(
            self.brand_panel,
            text='MOOC ROBOT',
            corner_radius=999,
            fg_color='#DDE9FF',
            text_color=self.COLORS['brand'],
            padx=12,
            pady=5,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=11, weight='bold'),
        ).pack(anchor='w', padx=18, pady=(18, 10))

        self.brand_title_label = ctk.CTkLabel(
            self.brand_panel,
            text='超星学习通自动作业助手',
            justify='left',
            anchor='w',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=28, weight='bold'),
            wraplength=220,
        )
        self.brand_title_label.pack(anchor='w', padx=18, pady=(0, 18))
        self._register_wrap_label(self.brand_title_label, self.brand_panel, padding=36, min_wrap=150, max_wrap=320)

        self._build_driver_card()
        self._build_config_card()
        self._build_login_card()
        self._build_log_card()

    def _build_main_workspace(self):
        self._build_parallel_section()
        self._build_solve_section()
        self._build_result_section()
        self._build_qa_section()

    def _build_driver_card(self):
        _card, content, _toggle = self._create_sidebar_card('驱动状态')

        top_row = ctk.CTkFrame(content, fg_color='transparent')
        top_row.pack(fill='x')
        self.driver_badge = self._make_badge(top_row, '未检测', tone='neutral')
        self.driver_badge.pack(side='left')

        self.driver_summary_label = self._make_wrap_label(
            content,
            textvariable=self.driver_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=0,
            min_wrap=150,
            max_wrap=320,
            container=content,
        )
        self.driver_summary_label.pack(anchor='w', pady=(10, 0))

        self.driver_button_row = ctk.CTkFrame(content, fg_color='transparent')
        self.driver_button_row.pack(fill='x', pady=(12, 0))
        for column in range(3):
            self.driver_button_row.grid_columnconfigure(column, weight=1)

        self.browse_driver_button = self._make_button(
            self.driver_button_row,
            '选择目录',
            self._choose_driver_directory,
            height=34,
            text_color=self.COLORS['text_primary'],
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
        )
        self.browse_driver_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))

        self.clear_driver_button = self._make_button(
            self.driver_button_row,
            '清空',
            self._clear_driver_directory,
            height=34,
            text_color=self.COLORS['text_primary'],
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
        )
        self.clear_driver_button.grid(row=0, column=1, sticky='ew', padx=4)

        self.refresh_driver_button = self._make_button(
            self.driver_button_row,
            '重检',
            self._refresh_driver_status,
            height=34,
        )
        self.refresh_driver_button.grid(row=0, column=2, sticky='ew', padx=(4, 0))

        self.driver_available_label = self._make_wrap_label(
            content,
            textvariable=self.driver_available_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=0,
            min_wrap=150,
            max_wrap=320,
            container=content,
        )
        self.driver_available_label.pack(anchor='w', pady=(12, 0))

        self.driver_missing_label = self._make_wrap_label(
            content,
            textvariable=self.driver_missing_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=0,
            min_wrap=150,
            max_wrap=320,
            container=content,
        )
        self.driver_missing_label.pack(anchor='w', pady=(6, 0))

        self._register_button_group(
            self.driver_button_row,
            [self.browse_driver_button, self.clear_driver_button, self.refresh_driver_button],
        )

    def _build_config_card(self):
        _card, content, toggle = self._create_sidebar_card(
            '配置管理',
            section_name='config',
            toggle_labels=('展开编辑', '收起'),
        )

        summary_box = ctk.CTkFrame(
            content,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=16,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        summary_box.pack(fill='x')

        self.config_summary_label = self._make_wrap_label(
            summary_box,
            textvariable=self.config_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=28,
            min_wrap=150,
            max_wrap=300,
            container=summary_box,
        )
        self.config_summary_label.pack(fill='x', padx=14, pady=12)

        body = self._create_section_body(
            content,
            'config',
            toggle,
            expanded=False,
            pady=(12, 0),
            toggle_labels=('展开编辑', '收起'),
        )
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body,
            text='作业地址',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13, weight='bold'),
        ).grid(row=0, column=0, sticky='w')

        self.address_entry = ctk.CTkEntry(
            body,
            height=38,
            corner_radius=14,
            border_color=self.COLORS['border'],
            placeholder_text='输入或粘贴作业页面地址',
        )
        self.address_entry.grid(row=1, column=0, sticky='ew', pady=(8, 12))

        ctk.CTkLabel(
            body,
            text='Cookie',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13, weight='bold'),
        ).grid(row=2, column=0, sticky='w')

        self.cookie_textbox = self._build_textbox(body, height=96, readonly=False)
        self.cookie_textbox.grid(row=3, column=0, sticky='ew', pady=(8, 12))

        ctk.CTkLabel(
            body,
            text='API Key',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13, weight='bold'),
        ).grid(row=4, column=0, sticky='w')

        self.api_entry = ctk.CTkEntry(
            body,
            height=38,
            corner_radius=14,
            border_color=self.COLORS['border'],
            placeholder_text='输入 DeepSeek API Key',
            show='*',
        )
        self.api_entry.grid(row=5, column=0, sticky='ew', pady=(8, 12))

        self.config_button_row = ctk.CTkFrame(body, fg_color='transparent')
        self.config_button_row.grid(row=6, column=0, sticky='ew')
        for column in range(2):
            self.config_button_row.grid_columnconfigure(column, weight=1)

        self.save_config_button = self._make_button(
            self.config_button_row,
            '保存配置',
            self._save_config,
            height=36,
        )
        self.save_config_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))

        self.reload_config_button = self._make_button(
            self.config_button_row,
            '重新读取',
            self._load_config_into_form,
            height=36,
            text_color=self.COLORS['text_primary'],
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
        )
        self.reload_config_button.grid(row=0, column=1, sticky='ew', padx=(4, 0))

        self.address_entry.bind('<KeyRelease>', lambda _event: self._refresh_config_summary())
        self.api_entry.bind('<KeyRelease>', lambda _event: self._refresh_config_summary())
        self.cookie_textbox._textbox.bind('<KeyRelease>', lambda _event: self._refresh_config_summary())

        self._register_button_group(
            self.config_button_row,
            [self.save_config_button, self.reload_config_button],
        )

    def _build_login_card(self):
        _card, content, _toggle = self._create_sidebar_card('登录获取 Cookie')

        top_row = ctk.CTkFrame(content, fg_color='transparent')
        top_row.pack(fill='x')
        self.login_badge = self._make_badge(top_row, '等待开始', tone='neutral')
        self.login_badge.pack(side='left')

        self.login_status_label = self._make_wrap_label(
            content,
            textvariable=self.login_status_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=0,
            min_wrap=150,
            max_wrap=320,
            container=content,
        )
        self.login_status_label.pack(anchor='w', pady=(10, 0))

        self.browser_segment = ctk.CTkSegmentedButton(
            content,
            values=list(self.BROWSER_SEGMENTS.keys()),
            variable=self.browser_segment_var,
            height=38,
            corner_radius=14,
            fg_color='#E8EFF8',
            selected_color=self.COLORS['brand'],
            selected_hover_color=self.COLORS['brand_hover'],
            unselected_color='#E8EFF8',
            unselected_hover_color='#DCE7F4',
            text_color='#24425E',
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12, weight='bold'),
        )
        self.browser_segment.pack(fill='x', pady=(12, 0))

        self.start_login_button = self._make_button(
            content,
            '开始登录',
            self._start_login_flow,
            height=38,
        )
        self.start_login_button.pack(fill='x', pady=(12, 0))

        self.login_button_row = ctk.CTkFrame(content, fg_color='transparent')
        self.login_button_row.pack(fill='x', pady=(8, 0))
        for column in range(2):
            self.login_button_row.grid_columnconfigure(column, weight=1)

        self.check_login_button = self._make_button(
            self.login_button_row,
            '开始检查',
            self._request_login_check,
            height=34,
            state='disabled',
            text_color=self.COLORS['text_primary'],
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
        )
        self.check_login_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))

        self.cancel_login_button = self._make_button(
            self.login_button_row,
            '取消登录',
            self._cancel_login_flow,
            height=34,
            state='disabled',
            fg_color=self.COLORS['danger_soft'],
            hover_color='#F8D8DE',
            text_color=self.COLORS['danger'],
        )
        self.cancel_login_button.grid(row=0, column=1, sticky='ew', padx=(4, 0))

        self._register_button_group(
            self.login_button_row,
            [self.check_login_button, self.cancel_login_button],
        )

    def _build_log_card(self):
        _card, content, toggle = self._create_sidebar_card(
            '运行日志',
            section_name='log',
            toggle_labels=('展开日志', '收起'),
        )

        summary_box = ctk.CTkFrame(
            content,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=16,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        summary_box.pack(fill='x')

        self.log_summary_label = self._make_wrap_label(
            summary_box,
            textvariable=self.log_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            padding=28,
            min_wrap=150,
            max_wrap=300,
            container=summary_box,
        )
        self.log_summary_label.pack(fill='x', padx=14, pady=12)

        body = self._create_section_body(
            content,
            'log',
            toggle,
            expanded=False,
            pady=(12, 0),
            toggle_labels=('展开日志', '收起'),
        )
        body.grid_columnconfigure(0, weight=1)

        self.clear_log_button = self._make_button(
            body,
            '清空日志',
            self._clear_logs,
            height=34,
            text_color=self.COLORS['text_primary'],
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
        )
        self.clear_log_button.grid(row=0, column=0, sticky='ew')

        self.log_textbox = self._build_textbox(body, height=180)
        self.log_textbox.grid(row=1, column=0, sticky='ew', pady=(10, 0))

    def _build_solve_section(self):
        body = self._create_stage_card('solve', '作业解答', collapsible=False)
        body.grid_columnconfigure(0, weight=1)

        mode_row = ctk.CTkFrame(body, fg_color='transparent')
        mode_row.grid(row=0, column=0, sticky='ew')
        mode_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            mode_row,
            text='AI 模式',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w')

        self.ai_segment = ctk.CTkSegmentedButton(
            mode_row,
            values=list(self.AI_SEGMENTS.keys()),
            variable=self.ai_segment_var,
            height=42,
            corner_radius=16,
            fg_color='#E8EFF8',
            selected_color=self.COLORS['brand'],
            selected_hover_color=self.COLORS['brand_hover'],
            unselected_color='#E8EFF8',
            unselected_hover_color='#DCE7F4',
            text_color='#24425E',
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12, weight='bold'),
        )
        self.ai_segment.grid(row=1, column=0, sticky='ew', pady=(10, 0))

        self.solve_action_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.solve_action_panel.grid(row=1, column=0, sticky='ew', pady=(18, 0))
        self.solve_action_panel.grid_columnconfigure(0, weight=1)
        self.solve_action_panel.grid_columnconfigure(1, weight=0)

        self.solve_info_col = ctk.CTkFrame(self.solve_action_panel, fg_color='transparent')
        self.solve_info_col.grid(row=0, column=0, sticky='ew', padx=18, pady=18)
        self.solve_info_col.grid_columnconfigure(0, weight=1)

        self.question_count_label = self._make_wrap_label(
            self.solve_info_col,
            textvariable=self.question_count_var,
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=15, weight='bold'),
            padding=0,
            min_wrap=240,
            max_wrap=700,
            container=self.solve_info_col,
        )
        self.question_count_label.grid(row=0, column=0, sticky='w')

        self.question_types_label = self._make_wrap_label(
            self.solve_info_col,
            textvariable=self.question_types_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            padding=0,
            min_wrap=240,
            max_wrap=700,
            container=self.solve_info_col,
        )
        self.question_types_label.grid(row=1, column=0, sticky='w', pady=(6, 0))

        self.solve_button = self._make_button(
            self.solve_action_panel,
            '开始抓题并解答',
            self._start_solve_flow,
            width=220,
            height=46,
        )
        self.solve_button.grid(row=0, column=1, sticky='e', padx=(0, 18), pady=18)

    def _build_result_section(self):
        body = self._create_stage_card('result', '结果与自动填写', collapsible=True, expanded=False)
        self.result_body = body
        body.grid_columnconfigure(0, weight=58)
        body.grid_columnconfigure(1, weight=42)

        self.result_strip = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.result_strip.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.result_strip.grid_columnconfigure(0, weight=1)
        self.result_strip.grid_columnconfigure(1, weight=0)

        self.result_summary_col = ctk.CTkFrame(self.result_strip, fg_color='transparent')
        self.result_summary_col.grid(row=0, column=0, sticky='ew', padx=18, pady=16)
        self.result_summary_col.grid_columnconfigure(0, weight=1)

        self.result_badge = self._make_badge(self.result_summary_col, '等待解题', tone='neutral')
        self.result_badge.grid(row=0, column=0, sticky='w')

        self.result_summary_label = self._make_wrap_label(
            self.result_summary_col,
            textvariable=self.result_summary_var,
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=15, weight='bold'),
            padding=0,
            min_wrap=240,
            max_wrap=680,
            container=self.result_summary_col,
        )
        self.result_summary_label.grid(row=1, column=0, sticky='w', pady=(10, 0))

        self.autofill_summary_label = self._make_wrap_label(
            self.result_summary_col,
            textvariable=self.autofill_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            padding=0,
            min_wrap=240,
            max_wrap=680,
            container=self.result_summary_col,
        )
        self.autofill_summary_label.grid(row=2, column=0, sticky='w', pady=(6, 0))

        self.autofill_button = self._make_button(
            self.result_strip,
            '自动填写到网页',
            self._start_autofill_flow,
            width=190,
            height=42,
            state='disabled',
        )
        self.autofill_button.grid(row=0, column=1, sticky='e', padx=(0, 18), pady=18)

        self.result_raw_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.result_raw_panel.grid(row=1, column=0, sticky='nsew', padx=(0, 10), pady=(16, 0))
        self.result_raw_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.result_raw_panel,
            text='原始 AI 输出',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w', padx=18, pady=(16, 8))

        self.raw_result_textbox = self._build_textbox(self.result_raw_panel, height=300)
        self.raw_result_textbox.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))

        self.result_structured_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.result_structured_panel.grid(row=1, column=1, sticky='nsew', padx=(10, 0), pady=(16, 0))
        self.result_structured_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.result_structured_panel,
            text='结构化答案 / 解析信息',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w', padx=18, pady=(16, 8))

        self.structured_result_textbox = self._build_textbox(self.result_structured_panel, height=300)
        self.structured_result_textbox.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))

    def _build_qa_section(self):
        body = self._create_stage_card('qa', '问答追问', collapsible=True, expanded=False)
        body.grid_columnconfigure(0, weight=1)

        self.qa_prompt_strip = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.qa_prompt_strip.grid(row=0, column=0, sticky='ew')
        self.qa_prompt_strip.grid_columnconfigure(0, weight=1)
        self.qa_prompt_strip.grid_columnconfigure(1, weight=0)

        self.qa_entry = ctk.CTkEntry(
            self.qa_prompt_strip,
            height=42,
            corner_radius=16,
            border_color=self.COLORS['border'],
            placeholder_text='例如：第 3 题为什么选这个答案？',
        )
        self.qa_entry.grid(row=0, column=0, sticky='ew', padx=18, pady=18)

        self.ask_button = self._make_button(
            self.qa_prompt_strip,
            '继续追问',
            self._start_followup_flow,
            width=156,
            height=42,
            state='disabled',
        )
        self.ask_button.grid(row=0, column=1, sticky='e', padx=(0, 18), pady=18)

        answer_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        answer_panel.grid(row=1, column=0, sticky='ew', pady=(16, 0))
        answer_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            answer_panel,
            text='问答回复',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w', padx=18, pady=(16, 8))

        self.qa_answer_textbox = self._build_textbox(answer_panel, height=300)
        self.qa_answer_textbox.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))

    def _build_parallel_section(self):
        body = self._create_stage_card('parallel', '课程并发中心', collapsible=True, expanded=True)
        body.grid_columnconfigure(0, weight=1)

        self.parallel_action_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['panel_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.parallel_action_panel.grid(row=0, column=0, sticky='ew')
        for column in range(4):
            self.parallel_action_panel.grid_columnconfigure(column, weight=1)

        self.parallel_load_courses_button = self._make_button(
            self.parallel_action_panel,
            '载入课程列表',
            self._start_load_course_catalog,
            height=40,
        )
        self.parallel_load_courses_button.grid(row=0, column=0, sticky='ew', padx=(18, 6), pady=18)

        self.parallel_load_tasks_button = self._make_button(
            self.parallel_action_panel,
            '载入所选课程任务',
            self._start_load_selected_course_tasks,
            height=40,
            state='disabled',
        )
        self.parallel_load_tasks_button.grid(row=0, column=1, sticky='ew', padx=6, pady=18)

        self.parallel_run_button = self._make_button(
            self.parallel_action_panel,
            f'并发运行 ({DEFAULT_PARALLEL_LIMIT})',
            self._start_parallel_run,
            height=40,
            state='disabled',
        )
        self.parallel_run_button.grid(row=0, column=2, sticky='ew', padx=6, pady=18)

        self.parallel_stop_button = self._make_button(
            self.parallel_action_panel,
            '停止并发',
            self._request_stop_parallel_run,
            height=40,
            fg_color=self.COLORS['danger'],
            hover_color='#BF3E4F',
            state='disabled',
        )
        self.parallel_stop_button.grid(row=0, column=3, sticky='ew', padx=(6, 18), pady=18)

        self.parallel_summary_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.parallel_summary_panel.grid(row=1, column=0, sticky='ew', pady=(16, 0))
        self.parallel_summary_panel.grid_columnconfigure(0, weight=1)

        self.parallel_course_summary_label = self._make_wrap_label(
            self.parallel_summary_panel,
            textvariable=self.course_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            padding=36,
            min_wrap=240,
            max_wrap=880,
            container=self.parallel_summary_panel,
        )
        self.parallel_course_summary_label.grid(row=0, column=0, sticky='w', padx=18, pady=(16, 0))

        self.parallel_task_summary_label = self._make_wrap_label(
            self.parallel_summary_panel,
            textvariable=self.task_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            padding=36,
            min_wrap=240,
            max_wrap=880,
            container=self.parallel_summary_panel,
        )
        self.parallel_task_summary_label.grid(row=1, column=0, sticky='w', padx=18, pady=(8, 0))

        self.parallel_run_summary_label = self._make_wrap_label(
            self.parallel_summary_panel,
            textvariable=self.parallel_summary_var,
            text_color=self.COLORS['text_secondary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13),
            padding=36,
            min_wrap=240,
            max_wrap=880,
            container=self.parallel_summary_panel,
        )
        self.parallel_run_summary_label.grid(row=2, column=0, sticky='w', padx=18, pady=(8, 16))

        self.parallel_course_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.parallel_course_panel.grid(row=2, column=0, sticky='ew', pady=(16, 0))
        self.parallel_course_panel.grid_columnconfigure(0, weight=1)
        self.parallel_course_panel.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            self.parallel_course_panel,
            text='课程选择',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w', padx=18, pady=(16, 8))

        self.parallel_course_toggle = self._make_button(
            self.parallel_course_panel,
            '收起',
            lambda: self._toggle_section('parallel-course-selection'),
            width=88,
            height=32,
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
            text_color=self.COLORS['text_primary'],
        )
        self.parallel_course_toggle.grid(row=0, column=1, sticky='e', padx=(0, 18), pady=(16, 8))

        self.parallel_course_body_host = ctk.CTkFrame(self.parallel_course_panel, fg_color='transparent')
        self.parallel_course_body_host.grid(row=1, column=0, columnspan=2, sticky='ew', padx=18, pady=0)
        self.parallel_course_body_host.grid_columnconfigure(0, weight=1)
        self.parallel_course_container = self._create_section_body(
            self.parallel_course_body_host,
            'parallel-course-selection',
            self.parallel_course_toggle,
            expanded=True,
            pady=(0, 18),
            collapse_host=self.parallel_course_body_host,
        )

        self.parallel_task_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.parallel_task_panel.grid(row=3, column=0, sticky='ew', pady=(16, 0))
        self.parallel_task_panel.grid_columnconfigure(0, weight=1)

        self.parallel_task_header = ctk.CTkFrame(self.parallel_task_panel, fg_color='transparent')
        self.parallel_task_header.grid(row=0, column=0, sticky='ew', padx=18, pady=(16, 8))
        self.parallel_task_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.parallel_task_header,
            text='任务选择',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w')

        self.parallel_select_all_button = self._make_button(
            self.parallel_task_header,
            '全选',
            lambda: self._set_all_parallel_tasks(True),
            width=88,
            height=32,
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
            text_color=self.COLORS['text_primary'],
            state='disabled',
        )
        self.parallel_select_all_button.grid(row=0, column=1, sticky='e', padx=(8, 0))

        self.parallel_clear_selection_button = self._make_button(
            self.parallel_task_header,
            '清空',
            lambda: self._set_all_parallel_tasks(False),
            width=88,
            height=32,
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
            text_color=self.COLORS['text_primary'],
            state='disabled',
        )
        self.parallel_clear_selection_button.grid(row=0, column=2, sticky='e', padx=(8, 0))

        self.parallel_task_toggle = self._make_button(
            self.parallel_task_header,
            '收起',
            lambda: self._toggle_section('parallel-task-selection'),
            width=88,
            height=32,
            fg_color=self.COLORS['panel_bg'],
            hover_color=self.COLORS['panel_alt'],
            text_color=self.COLORS['text_primary'],
        )
        self.parallel_task_toggle.grid(row=0, column=3, sticky='e', padx=(8, 0))

        self.parallel_task_body_host = ctk.CTkFrame(self.parallel_task_panel, fg_color='transparent')
        self.parallel_task_body_host.grid(row=1, column=0, sticky='ew', padx=18, pady=0)
        self.parallel_task_body_host.grid_columnconfigure(0, weight=1)
        self.parallel_task_container = self._create_section_body(
            self.parallel_task_body_host,
            'parallel-task-selection',
            self.parallel_task_toggle,
            expanded=True,
            pady=(0, 18),
            collapse_host=self.parallel_task_body_host,
        )

        self.parallel_status_panel = ctk.CTkFrame(
            body,
            fg_color=self.COLORS['card_bg'],
            corner_radius=20,
            border_width=1,
            border_color=self.COLORS['border_soft'],
        )
        self.parallel_status_panel.grid(row=4, column=0, sticky='ew', pady=(16, 0))
        self.parallel_status_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.parallel_status_panel,
            text='并发运行面板',
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
        ).grid(row=0, column=0, sticky='w', padx=18, pady=(16, 8))

        self.parallel_count_strip = ctk.CTkFrame(self.parallel_status_panel, fg_color='transparent')
        self.parallel_count_strip.grid(row=1, column=0, sticky='ew', padx=18)
        for column in range(6):
            self.parallel_count_strip.grid_columnconfigure(column, weight=1)

        self.parallel_pending_label = self._make_badge(self.parallel_count_strip, self.parallel_pending_var.get(), tone='neutral')
        self.parallel_pending_label.grid(row=0, column=0, sticky='w', padx=(0, 6), pady=(0, 12))
        self.parallel_running_label = self._make_badge(self.parallel_count_strip, self.parallel_running_var.get(), tone='brand')
        self.parallel_running_label.grid(row=0, column=1, sticky='w', padx=6, pady=(0, 12))
        self.parallel_completed_label = self._make_badge(self.parallel_count_strip, self.parallel_completed_var.get(), tone='success')
        self.parallel_completed_label.grid(row=0, column=2, sticky='w', padx=6, pady=(0, 12))
        self.parallel_stopped_label = self._make_badge(self.parallel_count_strip, self.parallel_stopped_var.get(), tone='warning')
        self.parallel_stopped_label.grid(row=0, column=3, sticky='w', padx=6, pady=(0, 12))
        self.parallel_failed_label = self._make_badge(self.parallel_count_strip, self.parallel_failed_var.get(), tone='danger')
        self.parallel_failed_label.grid(row=0, column=4, sticky='w', padx=6, pady=(0, 12))
        self.parallel_manual_label = self._make_badge(self.parallel_count_strip, self.parallel_manual_var.get(), tone='warning')
        self.parallel_manual_label.grid(row=0, column=5, sticky='w', padx=(6, 0), pady=(0, 12))

        self.parallel_result_textbox = self._build_textbox(self.parallel_status_panel, height=240)
        self.parallel_result_textbox.grid(row=2, column=0, sticky='ew', padx=18, pady=(0, 18))
        self._set_textbox(self.parallel_result_textbox, '等待课程和任务载入。')

    def _build_parallel_group_header(self, parent, text):
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=13, weight='bold'),
        )

    def _parallel_task_type_label(self, task_type):
        return {
            'chapter': '章节',
            'homework': '作业',
            'exam': '考试',
        }.get(task_type, task_type)

    def _render_course_catalog(self):
        for child in self.parallel_course_container.winfo_children():
            child.destroy()
        self.course_button_meta = {}

        if not self.course_catalog:
            ctk.CTkLabel(
                self.parallel_course_container,
                text='暂未载入课程。',
                text_color=self.COLORS['text_muted'],
                font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            ).pack(anchor='w')
            self._request_layout_pass('parallel-courses-empty', measure=True)
            return

        for course in self.course_catalog:
            button = self._make_button(
                self.parallel_course_container,
                course.course_name,
                lambda url=course.course_url: self._toggle_course_selection(url),
                height=38,
                fg_color=self.COLORS['panel_bg'],
                hover_color=self.COLORS['panel_alt'],
                text_color=self.COLORS['text_primary'],
            )
            button.pack(fill='x', pady=(0, 10))
            self.course_button_meta[course.course_url] = {
                'button': button,
                'course': course,
            }
            self._sync_course_button_state(course.course_url)

        self._request_layout_pass('parallel-courses-render', measure=True)

    def _sync_course_button_state(self, course_url):
        meta = self.course_button_meta.get(course_url)
        if not meta:
            return
        button = meta['button']
        selected = course_url in self.selected_course_urls
        if selected:
            button.configure(
                fg_color=self.COLORS['brand_soft'],
                hover_color='#D7E6FF',
                text_color=self.COLORS['brand'],
            )
        else:
            button.configure(
                fg_color=self.COLORS['panel_bg'],
                hover_color=self.COLORS['panel_alt'],
                text_color=self.COLORS['text_primary'],
            )

    def _toggle_course_selection(self, course_url):
        if course_url in self.selected_course_urls:
            self.selected_course_urls.remove(course_url)
        else:
            self.selected_course_urls.add(course_url)

        for current_url in self.course_button_meta:
            self._sync_course_button_state(current_url)

        if self.task_catalog_by_course:
            self.task_catalog_by_course = {}
            self.task_targets_by_id = {}
            self.task_checkbox_vars = {}
            self.parallel_results = []
            self.parallel_task_states = {}
            self.task_summary_var.set('任务中心：课程选择已变化，请重新载入任务。')
            self.parallel_summary_var.set('并发运行：请重新载入任务后开始。')
            self._render_task_catalogs()
            self._set_textbox(self.parallel_result_textbox, '课程选择已变化，请重新载入任务。')
            self._refresh_parallel_status_counts()

        self.course_summary_var.set(
            f'课程中心：已载入 {len(self.course_catalog)} 门课程，已选择 {len(self.selected_course_urls)} 门。'
        )
        self._update_parallel_action_state()

    def _render_task_catalogs(self):
        for child in self.parallel_task_container.winfo_children():
            child.destroy()
        self.task_targets_by_id = {}
        self.task_checkbox_vars = {}

        ordered_catalogs = []
        for course in self.course_catalog:
            if course.course_url in self.task_catalog_by_course:
                ordered_catalogs.append(self.task_catalog_by_course[course.course_url])

        if not ordered_catalogs:
            ctk.CTkLabel(
                self.parallel_task_container,
                text='暂未载入任务。',
                text_color=self.COLORS['text_muted'],
                font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            ).pack(anchor='w')
            self._request_layout_pass('parallel-tasks-empty', measure=True)
            self._update_parallel_action_state()
            return

        for catalog in ordered_catalogs:
            course = catalog.get('course')
            if course is None:
                continue

            course_frame = ctk.CTkFrame(
                self.parallel_task_container,
                fg_color=self.COLORS['panel_bg'],
                corner_radius=18,
                border_width=1,
                border_color=self.COLORS['border_soft'],
            )
            course_frame.pack(fill='x', pady=(0, 14))
            course_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                course_frame,
                text=course.course_name,
                text_color=self.COLORS['text_primary'],
                font=ctk.CTkFont(family='Microsoft YaHei UI', size=14, weight='bold'),
            ).grid(row=0, column=0, sticky='w', padx=16, pady=(14, 6))

            row_index = 1
            group_specs = (
                ('chapters', '章节'),
                ('homework', '作业'),
                ('exams', '考试'),
            )
            has_any_item = False

            for group_key, group_label in group_specs:
                tasks = catalog.get(group_key) or []
                if not tasks:
                    continue
                has_any_item = True
                header = self._build_parallel_group_header(course_frame, group_label)
                header.grid(row=row_index, column=0, sticky='w', padx=16, pady=(10, 4))
                row_index += 1

                group_frame = ctk.CTkFrame(course_frame, fg_color='transparent')
                group_frame.grid(row=row_index, column=0, sticky='ew', padx=16)
                group_frame.grid_columnconfigure(0, weight=1)
                row_index += 1

                for task in tasks:
                    self.task_targets_by_id[task.task_id] = task
                    var = tk.BooleanVar(value=False)
                    self.task_checkbox_vars[task.task_id] = var
                    label = task.title
                    if task.task_type == 'chapter' and task.pending_count:
                        label += f'  (待完成 {task.pending_count})'
                    if task.status_text:
                        label += f'  [{task.status_text}]'

                    checkbox = ctk.CTkCheckBox(
                        group_frame,
                        text=label,
                        variable=var,
                        command=self._update_parallel_action_state,
                        fg_color=self.COLORS['brand'],
                        hover_color=self.COLORS['brand_hover'],
                        border_color=self.COLORS['border'],
                        checkmark_color='#FFFFFF',
                        text_color=self.COLORS['text_primary'],
                        font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
                    )
                    checkbox.pack(fill='x', pady=(0, 8))

            if not has_any_item:
                ctk.CTkLabel(
                    course_frame,
                    text='该课程暂无可识别的章节、作业或考试。',
                    text_color=self.COLORS['text_muted'],
                    font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
                ).grid(row=row_index, column=0, sticky='w', padx=16, pady=(8, 14))

        self._request_layout_pass('parallel-tasks-render', measure=True)
        self._update_parallel_action_state()

    def _collect_selected_parallel_targets(self):
        selected = []
        for task_id, var in self.task_checkbox_vars.items():
            if bool(var.get()) and task_id in self.task_targets_by_id:
                selected.append(self.task_targets_by_id[task_id])
        return selected

    def _set_all_parallel_tasks(self, selected):
        if not self.task_checkbox_vars:
            return
        for var in self.task_checkbox_vars.values():
            var.set(bool(selected))
        self._update_parallel_action_state()

    def _update_parallel_action_state(self):
        load_tasks_state = 'normal' if self.selected_course_urls and 'parallel_tasks' not in self.busy_tasks else 'disabled'
        run_state = 'normal' if self._collect_selected_parallel_targets() and 'parallel_run' not in self.busy_tasks else 'disabled'
        batch_select_state = 'normal' if self.task_checkbox_vars and 'parallel_tasks' not in self.busy_tasks and 'parallel_run' not in self.busy_tasks else 'disabled'
        stop_state = 'normal' if self.active_parallel_controller is not None and not self.parallel_stop_requested else 'disabled'

        if self.parallel_load_tasks_button.winfo_exists():
            self.parallel_load_tasks_button.configure(state=load_tasks_state)
        if self.parallel_run_button.winfo_exists():
            self.parallel_run_button.configure(state=run_state)
        if hasattr(self, 'parallel_stop_button') and self.parallel_stop_button.winfo_exists():
            self.parallel_stop_button.configure(state=stop_state)
        if hasattr(self, 'parallel_select_all_button') and self.parallel_select_all_button.winfo_exists():
            self.parallel_select_all_button.configure(state=batch_select_state)
        if hasattr(self, 'parallel_clear_selection_button') and self.parallel_clear_selection_button.winfo_exists():
            self.parallel_clear_selection_button.configure(state=batch_select_state)

    def _append_parallel_result_line(self, message):
        if not self.parallel_result_textbox.winfo_exists():
            return
        self.parallel_result_textbox.configure(state='normal')
        self.parallel_result_textbox.insert('end', str(message).rstrip() + '\n')
        self.parallel_result_textbox.see('end')
        self.parallel_result_textbox.configure(state='disabled')

    def _refresh_parallel_status_counts(self):
        counts = {
            'queued': 0,
            'running': 0,
            'completed': 0,
            'stopped': 0,
            'failed': 0,
            'manual_review': 0,
        }
        for state in self.parallel_task_states.values():
            if state in counts:
                counts[state] += 1

        self.parallel_pending_var.set(f"待启动：{counts['queued']}")
        self.parallel_running_var.set(f"进行中：{counts['running']}")
        self.parallel_completed_var.set(f"已完成：{counts['completed']}")
        self.parallel_stopped_var.set(f"已停止：{counts['stopped']}")
        self.parallel_failed_var.set(f"失败：{counts['failed']}")
        self.parallel_manual_var.set(f"待人工提交：{counts['manual_review']}")

        self.parallel_pending_label.configure(text=self.parallel_pending_var.get())
        self.parallel_running_label.configure(text=self.parallel_running_var.get())
        self.parallel_completed_label.configure(text=self.parallel_completed_var.get())
        self.parallel_stopped_label.configure(text=self.parallel_stopped_var.get())
        self.parallel_failed_label.configure(text=self.parallel_failed_var.get())
        self.parallel_manual_label.configure(text=self.parallel_manual_var.get())
        self._request_layout_pass('parallel-status-counts')

    def _reset_parallel_status(self, targets):
        self.parallel_task_states = {target.task_id: 'queued' for target in targets}
        self.parallel_results = []
        self._refresh_parallel_status_counts()
        self._set_textbox(self.parallel_result_textbox, '')
        for target in targets:
            self._append_parallel_result_line(
                f"[待启动] {target.course_name} | {target.title} | {self._parallel_task_type_label(target.task_type)}"
            )

    def _queue_parallel_event(self, payload):
        self.ui_queue.put({
            'kind': 'callback',
            'callback': lambda data=payload: self._handle_parallel_event(data),
        })

    def _handle_parallel_event(self, payload):
        event_name = payload.get('event')
        task_info = payload.get('task') or {}
        task_id = task_info.get('task_id', '')
        if not task_id:
            return

        if event_name == 'queued':
            self.parallel_task_states[task_id] = 'queued'
        elif event_name == 'started':
            self.parallel_task_states[task_id] = 'running'
            course_name = task_info.get('course_name', '')
            task_title = task_info.get('title', '')
            self.parallel_summary_var.set(f'并发运行：正在执行 {course_name} | {task_title}')
            self._append_parallel_result_line(
                f"[进行中] {task_info.get('course_name', '')} | {task_info.get('title', '')}"
            )
        elif event_name == 'finished':
            result_info = payload.get('result') or {}
            status = result_info.get('status', 'failed')
            self.parallel_task_states[task_id] = status
            label_map = {
                'completed': '已完成',
                'stopped': '已停止',
                'manual_review': '待人工提交',
                'failed': '失败',
            }
            course_name = task_info.get('course_name', '')
            task_title = task_info.get('title', '')
            detail = str(result_info.get('detail', '')).strip()
            summary = f'并发运行：{course_name} | {task_title} {label_map.get(status, status)}'
            if detail:
                summary += f'。{detail}'
            self.parallel_summary_var.set(summary)
            self._append_parallel_result_line(
                f"[{label_map.get(status, status)}] {course_name} | {task_title} | {detail}"
            )

        self._refresh_parallel_status_counts()

    def _start_load_course_catalog(self):
        cookie = self._read_textbox(self.cookie_textbox)
        browser_type = self._selected_browser()
        self._set_stage_focus('parallel')
        self.course_summary_var.set('课程中心：正在载入课程列表...')
        self.task_summary_var.set('任务中心：等待课程列表返回。')
        self.parallel_summary_var.set('并发运行：等待任务选择。')
        self.course_catalog = []
        self.selected_course_urls = set()
        self.task_catalog_by_course = {}
        self.task_targets_by_id = {}
        self.task_checkbox_vars = {}
        self.parallel_task_states = {}
        self.parallel_results = []
        self._render_course_catalog()
        self._render_task_catalogs()
        self._set_textbox(self.parallel_result_textbox, '正在载入课程列表...')
        self._refresh_parallel_status_counts()

        def target():
            return load_course_catalog(
                cookie=cookie,
                browser_type=browser_type,
                notify=self._notify_from_worker,
            )

        def on_success(courses):
            self.course_catalog = list(courses or [])
            self.course_summary_var.set(f'课程中心：已载入 {len(self.course_catalog)} 门课程，请点击按钮选择课程。')
            self._render_course_catalog()
            self._set_textbox(self.parallel_result_textbox, '课程列表已返回，请选择课程并载入任务。')
            self._update_parallel_action_state()
            if self.course_catalog:
                self._pulse_button(self.parallel_load_tasks_button)

        def on_error(error):
            self.course_summary_var.set('课程中心：课程列表载入失败。')
            self.task_summary_var.set('任务中心：请先成功载入课程。')
            self._set_textbox(self.parallel_result_textbox, '课程列表载入失败。')
            self._handle_task_error(error)

        def on_finally():
            self._update_parallel_action_state()

        self._run_task(
            'parallel_courses',
            [self.parallel_load_courses_button, self.browser_segment],
            target,
            on_success=on_success,
            on_error=on_error,
            on_finally=on_finally,
            duplicate_message='课程列表正在载入，请稍候。',
        )

    def _start_load_selected_course_tasks(self):
        selected_courses = [
            course
            for course in self.course_catalog
            if course.course_url in self.selected_course_urls
        ]
        if not selected_courses:
            self._append_log('warn', '请先至少选择一门课程。')
            return

        cookie = self._read_textbox(self.cookie_textbox)
        browser_type = self._selected_browser()
        self._set_stage_focus('parallel')
        self.task_summary_var.set('任务中心：正在载入所选课程任务...')
        self.parallel_summary_var.set('并发运行：等待任务选择。')
        self.task_catalog_by_course = {}
        self.task_targets_by_id = {}
        self.task_checkbox_vars = {}
        self.parallel_results = []
        self.parallel_task_states = {}
        self._render_task_catalogs()
        self._set_textbox(self.parallel_result_textbox, '正在载入所选课程任务...')
        self._refresh_parallel_status_counts()

        def target():
            catalogs = []
            for course in selected_courses:
                catalogs.append(load_course_task_catalog(
                    course_url=course.course_url,
                    cookie=cookie,
                    browser_type=browser_type,
                    notify=self._notify_from_worker,
                ))
            return catalogs

        def on_success(catalogs):
            self.task_catalog_by_course = {}
            total_tasks = 0
            for catalog in catalogs or []:
                course = catalog.get('course')
                if course is None:
                    continue
                self.task_catalog_by_course[course.course_url] = catalog
                total_tasks += len(catalog.get('chapters', []))
                total_tasks += len(catalog.get('homework', []))
                total_tasks += len(catalog.get('exams', []))

            self.task_summary_var.set(
                f'任务中心：已载入 {len(self.task_catalog_by_course)} 门课程，共 {total_tasks} 个可选任务。'
            )
            self._render_task_catalogs()
            self._set_textbox(self.parallel_result_textbox, '任务目录已返回，请勾选需要并发执行的任务。')
            if total_tasks:
                self._pulse_button(self.parallel_run_button)

        def on_error(error):
            self.task_summary_var.set('任务中心：任务目录载入失败。')
            self._set_textbox(self.parallel_result_textbox, '任务目录载入失败。')
            self._handle_task_error(error)

        def on_finally():
            self._update_parallel_action_state()

        self._run_task(
            'parallel_tasks',
            [self.parallel_load_tasks_button, self.parallel_load_courses_button],
            target,
            on_success=on_success,
            on_error=on_error,
            on_finally=on_finally,
            duplicate_message='任务目录正在载入，请稍候。',
        )

    def _request_stop_parallel_run(self):
        controller = self.active_parallel_controller
        if controller is None:
            return
        if self.parallel_stop_requested:
            return

        self.parallel_stop_requested = True
        self.parallel_summary_var.set('并发运行：正在停止，已向运行中的任务发送停止信号。')
        self._append_log('warn', '已请求停止并发运行，正在关闭活动浏览器...')
        self._append_parallel_result_line('[已请求停止] 正在终止进行中的并发任务。')
        self._update_parallel_action_state()
        threading.Thread(target=controller.request_stop, daemon=True).start()

    def _start_parallel_run(self):
        targets = self._collect_selected_parallel_targets()
        if not targets:
            self._append_log('warn', '请先勾选至少一个任务。')
            return

        cookie = self._read_textbox(self.cookie_textbox)
        api_key = self.api_entry.get().strip()
        ai_mode = self._selected_ai_mode()
        browser_type = self._selected_browser()
        controller = ParallelRunController()
        self.active_parallel_controller = controller
        self.parallel_controllers.append(controller)
        self.parallel_stop_requested = False

        self._set_stage_focus('parallel')
        contains_chapter_target = any(target.task_type == 'chapter' for target in targets)
        self.parallel_summary_var.set(
            (
                (
                    f'并发运行：作业/考试最多并发 {min(DEFAULT_PARALLEL_LIMIT, len(targets))} 个任务，'
                    '章节任务单独串行排队。'
                )
                if contains_chapter_target
                else f'并发运行：准备启动 {min(DEFAULT_PARALLEL_LIMIT, len(targets))} 个任务。'
            )
        )
        self._reset_parallel_status(targets)
        if contains_chapter_target:
            self._append_parallel_result_line('[混合调度] 章节任务将单独串行执行，作业/考试继续按并发槽位运行。')

        def target():
            return run_parallel_targets(
                targets=targets,
                cookie=cookie,
                api_key=api_key,
                ai_mode=ai_mode,
                browser_type=browser_type,
                max_parallel=DEFAULT_PARALLEL_LIMIT,
                notify=self._notify_from_worker,
                event_callback=self._queue_parallel_event,
                parallel_controller=controller,
            )

        def on_success(results):
            self.parallel_results = list(results or [])
            completed = sum(1 for result in self.parallel_results if result.status == 'completed')
            stopped = sum(1 for result in self.parallel_results if result.status == 'stopped')
            failed = sum(1 for result in self.parallel_results if result.status == 'failed')
            manual = sum(1 for result in self.parallel_results if result.status == 'manual_review')
            if stopped:
                self.parallel_summary_var.set(
                    f'并发运行：已停止，共 {len(self.parallel_results)} 项任务，已完成 {completed}，已停止 {stopped}，失败 {failed}，待人工提交 {manual}。'
                )
            else:
                self.parallel_summary_var.set(
                    f'并发运行：已结束，共 {len(self.parallel_results)} 项任务，已完成 {completed}，失败 {failed}，待人工提交 {manual}。'
                )
            self._refresh_parallel_status_counts()
            self._append_log(
                'success' if not stopped and not failed else 'info',
                (
                    f'并发运行结束：共 {len(self.parallel_results)} 项任务，'
                    f'已完成 {completed}，已停止 {stopped}，失败 {failed}，待人工提交 {manual}。'
                ),
            )
            self._append_parallel_result_line(
                (
                    '[运行结束] '
                    f'共 {len(self.parallel_results)} 项任务 | '
                    f'已完成 {completed} | 已停止 {stopped} | 失败 {failed} | 待人工提交 {manual}'
                )
            )

        def on_error(error):
            self.parallel_summary_var.set('并发运行：执行失败。')
            self._handle_task_error(error)

        def on_finally():
            self.active_parallel_controller = None
            self.parallel_stop_requested = False
            self._update_parallel_action_state()

        self._run_task(
            'parallel_run',
            [self.parallel_run_button, self.parallel_load_tasks_button, self.parallel_load_courses_button],
            target,
            on_success=on_success,
            on_error=on_error,
            on_finally=on_finally,
            duplicate_message='并发任务已经在运行中，请稍候。',
        )
        self._update_parallel_action_state()

    def _build_final_copy_state(self):
        pass

    def _bind_window_events(self):
        self.bind('<Configure>', self._on_root_configure, add='+')
        self.bind('<B1-Motion>', self._update_sidebar_drag, add='+')
        self.bind('<ButtonRelease-1>', self._finish_sidebar_drag, add='+')
        self.bind_all('<MouseWheel>', self._on_global_mousewheel, add='+')
        self.bind_all('<Button-4>', lambda event: self._on_global_mousewheel(event, units=-1), add='+')
        self.bind_all('<Button-5>', lambda event: self._on_global_mousewheel(event, units=1), add='+')

        for widget in (self.sidebar_resize_handle, self.sidebar_resize_bar):
            widget.bind('<Enter>', lambda _event: self._set_splitter_state('hover'))
            widget.bind('<Leave>', lambda _event: self._set_splitter_state('idle'))
            widget.bind('<ButtonPress-1>', self._start_sidebar_drag)

    def _on_root_configure(self, event):
        if not self.ui_ready:
            return
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if size == self.last_root_size:
            return
        self.last_root_size = size
        current_width = max(event.width, self.MIN_WINDOW_WIDTH)
        self.sidebar_max_width = max(
            self.MIN_SIDEBAR_WIDTH,
            min(self.MAX_SIDEBAR_WIDTH, current_width - self.MIN_MAIN_WIDTH),
        )
        if self.sidebar_width > self.sidebar_max_width:
            self._apply_sidebar_width(self.sidebar_max_width)
        self._request_layout_pass('root-configure')

    def _on_scroller_canvas_configure(self, scroller, width):
        if not self.ui_ready:
            return
        width = max(int(width or 0), 1)
        if width == scroller['canvas_width']:
            return
        scroller['canvas_width'] = width
        self._sync_canvas_window_width(scroller, width)
        self._request_layout_pass(f"{scroller['name']}-canvas")

    def _on_scroller_content_configure(self, scroller):
        self._sync_scroll_region(scroller)

    def _sync_canvas_window_width(self, scroller, width):
        width = max(int(width or 0), 1)
        scroller['canvas'].itemconfigure(scroller['window_id'], width=width)

    def _sync_scroll_region(self, scroller):
        bbox = scroller['canvas'].bbox('all')
        scroller['canvas'].configure(scrollregion=bbox or (0, 0, 0, 0))

    def _sync_all_scroll_regions(self):
        self._sync_scroll_region(self.sidebar_scroller)
        self._sync_scroll_region(self.main_scroller)

    def _set_active_scroller(self, scroller):
        self.active_scroller = scroller

    def _on_global_mousewheel(self, event, units=None):
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if widget is None:
            return
        if widget.winfo_class() in {'Text', 'Entry', 'TEntry'}:
            return

        scroller = self._resolve_scroller_for_pointer(widget)
        if not scroller:
            return

        if units is None:
            delta = event.delta
            if delta == 0:
                return
            units = -1 * int(delta / 120)
            if units == 0:
                units = -1 if delta > 0 else 1

        self._scroll_canvas(scroller, units)

    def _resolve_scroller_for_pointer(self, widget):
        if self._is_descendant(widget, self.sidebar_shell):
            return self.sidebar_scroller
        if self._is_descendant(widget, self.main_shell):
            return self.main_scroller
        return self.active_scroller

    def _scroll_canvas(self, scroller, units):
        if not scroller:
            return
        canvas = scroller['canvas']
        start, end = canvas.yview()
        if start == 0.0 and end == 1.0:
            return
        canvas.yview_scroll(int(units), 'units')

    def _is_descendant(self, widget, ancestor):
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = getattr(current, 'master', None)
        return False

    def _request_layout_pass(self, _reason='layout', measure=False):
        if not self.ui_ready:
            return
        if measure:
            self.layout_measure_requested = True
        if self.layout_pass_pending:
            return
        self.layout_pass_pending = True
        self.layout_after_id = self.after_idle(self._commit_layout_pass)

    def _commit_layout_pass(self):
        self.layout_pass_pending = False
        self.layout_after_id = None
        if not self.winfo_exists():
            return

        self._apply_sidebar_width(self.sidebar_width)
        self._sync_canvas_window_width(self.sidebar_scroller, self.sidebar_scroller['canvas'].winfo_width())
        self._sync_canvas_window_width(self.main_scroller, self.main_scroller['canvas'].winfo_width())

        main_width = max(self.main_scroller['canvas'].winfo_width(), self.main_shell.winfo_width(), self.MIN_MAIN_WIDTH)
        breakpoint_changed = self._apply_breakpoint_layout(main_width)
        wrap_changed = self._update_wrap_labels()

        if breakpoint_changed:
            self._request_layout_pass('breakpoint-followup', measure=True)

        if wrap_changed:
            self.layout_measure_requested = True

        self._measure_sections_if_dirty()

    def _measure_sections_if_dirty(self):
        if not self.layout_measure_requested:
            return
        self.layout_measure_requested = False
        self._request_scroll_region_sync()

    def _request_scroll_region_sync(self):
        if self.scroll_sync_after_id is not None or not self.winfo_exists():
            return
        self.scroll_sync_after_id = self.after_idle(self._flush_scroll_region_sync)

    def _flush_scroll_region_sync(self):
        self.scroll_sync_after_id = None
        if not self.winfo_exists():
            return
        self._sync_all_scroll_regions()

    def _apply_sidebar_width(self, width):
        current_width = max(self.winfo_width(), self.MIN_WINDOW_WIDTH)
        self.sidebar_max_width = max(
            self.MIN_SIDEBAR_WIDTH,
            min(self.MAX_SIDEBAR_WIDTH, current_width - self.MIN_MAIN_WIDTH),
        )
        clamped = max(self.MIN_SIDEBAR_WIDTH, min(int(width), self.sidebar_max_width))
        self.sidebar_width = clamped
        if self.applied_sidebar_width != clamped:
            self.applied_sidebar_width = clamped
            self.sidebar_shell.configure(width=clamped)
            self.grid_columnconfigure(0, minsize=clamped)
        return clamped

    def _apply_breakpoint_layout(self, main_width):
        changed = False

        compact_sidebar = self.sidebar_width < self.COMPACT_SIDEBAR_THRESHOLD
        if compact_sidebar != self.sidebar_compact:
            self.sidebar_compact = compact_sidebar
            self._apply_sidebar_button_layout(compact_sidebar)
            changed = True

        main_actions_stacked = main_width < self.MAIN_ACTION_STACK_THRESHOLD
        if main_actions_stacked != self.main_actions_stacked:
            self.main_actions_stacked = main_actions_stacked
            self._apply_main_action_layout(main_actions_stacked)
            changed = True

        qa_actions_stacked = main_width < self.MAIN_ACTION_STACK_THRESHOLD
        if qa_actions_stacked != self.qa_actions_stacked:
            self.qa_actions_stacked = qa_actions_stacked
            self._apply_qa_action_layout(qa_actions_stacked)
            changed = True

        result_stacked = main_width < self.RESULT_STACK_THRESHOLD
        if result_stacked != self.result_stacked:
            self.result_stacked = result_stacked
            self._apply_result_layout(result_stacked)
            changed = True

        return changed

    def _register_button_group(self, frame, widgets):
        self.sidebar_button_groups.append({
            'frame': frame,
            'widgets': widgets,
            'compact': None,
        })

    def _apply_sidebar_button_layout(self, compact):
        for group in self.sidebar_button_groups:
            if group['compact'] == compact:
                continue

            frame = group['frame']
            widgets = group['widgets']
            if compact:
                for column in range(len(widgets)):
                    frame.grid_columnconfigure(column, weight=0)
                frame.grid_columnconfigure(0, weight=1)
                for index, widget in enumerate(widgets):
                    widget.grid_configure(
                        row=index,
                        column=0,
                        sticky='ew',
                        padx=0,
                        pady=(0, 8) if index < len(widgets) - 1 else 0,
                    )
            else:
                for column in range(len(widgets)):
                    frame.grid_columnconfigure(column, weight=1)
                for index, widget in enumerate(widgets):
                    widget.grid_configure(
                        row=0,
                        column=index,
                        sticky='ew',
                        padx=self._inline_button_pad(index, len(widgets)),
                        pady=0,
                    )
            group['compact'] = compact

    def _apply_main_action_layout(self, stacked):
        self.solve_action_panel.grid_columnconfigure(0, weight=1)
        self.solve_action_panel.grid_columnconfigure(1, weight=0)
        if stacked:
            self.solve_info_col.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=(18, 10))
            self.solve_button.grid_configure(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))
        else:
            self.solve_info_col.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=18)
            self.solve_button.grid_configure(row=0, column=1, sticky='e', padx=(0, 18), pady=18)

    def _apply_qa_action_layout(self, stacked):
        self.qa_prompt_strip.grid_columnconfigure(0, weight=1)
        self.qa_prompt_strip.grid_columnconfigure(1, weight=0)
        if stacked:
            self.qa_entry.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=(18, 10))
            self.ask_button.grid_configure(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))
        else:
            self.qa_entry.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=18)
            self.ask_button.grid_configure(row=0, column=1, sticky='e', padx=(0, 18), pady=18)

    def _apply_result_layout(self, stacked):
        if stacked:
            self.result_body.grid_columnconfigure(0, weight=1)
            self.result_body.grid_columnconfigure(1, weight=0)
            self.result_summary_col.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=(16, 10))
            self.autofill_button.grid_configure(row=1, column=0, sticky='ew', padx=18, pady=(0, 18))
            self.result_raw_panel.grid_configure(row=1, column=0, columnspan=2, sticky='nsew', padx=0, pady=(16, 0))
            self.result_structured_panel.grid_configure(row=2, column=0, columnspan=2, sticky='nsew', padx=0, pady=(16, 0))
        else:
            self.result_body.grid_columnconfigure(0, weight=58)
            self.result_body.grid_columnconfigure(1, weight=42)
            self.result_summary_col.grid_configure(row=0, column=0, sticky='ew', padx=18, pady=16)
            self.autofill_button.grid_configure(row=0, column=1, sticky='e', padx=(0, 18), pady=18)
            self.result_raw_panel.grid_configure(row=1, column=0, columnspan=1, sticky='nsew', padx=(0, 10), pady=(16, 0))
            self.result_structured_panel.grid_configure(row=1, column=1, columnspan=1, sticky='nsew', padx=(10, 0), pady=(16, 0))

    def _register_wrap_label(self, widget, container, padding=24, min_wrap=120, max_wrap=None):
        self.wrap_labels.append({
            'widget': widget,
            'container': container,
            'padding': padding,
            'min_wrap': min_wrap,
            'max_wrap': max_wrap,
            'last_wrap': min_wrap,
        })

    def _update_wrap_labels(self):
        changed = False
        for meta in self.wrap_labels:
            widget = meta['widget']
            container = meta['container']
            if not widget.winfo_exists() or not container.winfo_exists():
                continue

            container_width = container.winfo_width() or container.winfo_reqwidth()
            if container_width <= 1:
                continue

            wraplength = max(meta['min_wrap'], container_width - meta['padding'])
            if meta['max_wrap'] is not None:
                wraplength = min(wraplength, meta['max_wrap'])

            current = meta.get('last_wrap', meta['min_wrap'])
            if abs(current - wraplength) >= self.WRAP_DELTA:
                widget.configure(wraplength=wraplength)
                meta['last_wrap'] = wraplength
                changed = True
        return changed

    def _start_sidebar_drag(self, event):
        self.is_sidebar_resizing = True
        self.drag_origin_x = event.x_root
        self.drag_origin_width = self.sidebar_width
        self._set_splitter_state('active', animate=False)

    def _update_sidebar_drag(self, event):
        if not self.is_sidebar_resizing:
            return
        delta = event.x_root - self.drag_origin_x
        self._apply_sidebar_width(self.drag_origin_width + delta)
        self._sync_canvas_window_width(self.sidebar_scroller, self.sidebar_scroller['canvas'].winfo_width())
        self._request_layout_pass('sidebar-drag')

    def _finish_sidebar_drag(self, _event=None):
        if not self.is_sidebar_resizing:
            return
        self.is_sidebar_resizing = False
        self._set_splitter_state('idle')
        self._request_layout_pass('sidebar-drag-finish', measure=True)

    def _create_sidebar_card(self, title, section_name=None, toggle_labels=None):
        card = ctk.CTkFrame(
            self.sidebar_scroll,
            fg_color=self.COLORS['card_bg'],
            corner_radius=18,
            border_width=1,
            border_color=self.COLORS['border'],
        )
        card.pack(fill='x', pady=(0, 12))

        header = ctk.CTkFrame(card, fg_color='transparent')
        header.pack(fill='x', padx=18, pady=(16, 12))

        ctk.CTkLabel(
            header,
            text=title,
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=16, weight='bold'),
        ).pack(side='left', anchor='w')

        toggle = None
        if section_name:
            labels = toggle_labels or ('展开', '收起')
            toggle = self._make_button(
                header,
                labels[0],
                lambda name=section_name: self._toggle_section(name),
                height=30,
                width=88,
                fg_color=self.COLORS['panel_bg'],
                hover_color=self.COLORS['panel_alt'],
                text_color=self.COLORS['text_primary'],
            )
            toggle.pack(side='right')

        content = ctk.CTkFrame(card, fg_color='transparent')
        content.pack(fill='x', padx=18, pady=(0, 16))
        return card, content, toggle

    def _create_stage_card(self, stage_name, title, collapsible=False, expanded=False):
        card = ctk.CTkFrame(
            self.main_scroll,
            fg_color=self.COLORS['card_bg'],
            corner_radius=24,
            border_width=1,
            border_color=self.COLORS['border'],
        )
        card.pack(fill='x', pady=(0, 18))
        card._current_border_color = self.COLORS['border']

        header = ctk.CTkFrame(card, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(22, 14))

        text_col = ctk.CTkFrame(header, fg_color='transparent')
        text_col.pack(side='left', fill='x', expand=True)

        title_label = ctk.CTkLabel(
            text_col,
            text=title,
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=22, weight='bold'),
        )
        title_label.pack(anchor='w')

        toggle = None
        if collapsible:
            toggle = self._make_button(
                header,
                '展开',
                lambda name=stage_name: self._toggle_section(name),
                height=34,
                width=90,
                fg_color=self.COLORS['panel_bg'],
                hover_color=self.COLORS['panel_alt'],
                text_color=self.COLORS['text_primary'],
            )
            toggle.pack(side='right')

        body_host = ctk.CTkFrame(card, fg_color='transparent')
        body_host.pack(fill='x', padx=24)
        body_host.configure(height=0 if collapsible and not expanded else 1)

        if collapsible:
            body = self._create_section_body(
                body_host,
                stage_name,
                toggle,
                expanded=expanded,
                pady=(0, 24),
                toggle_labels=('展开', '收起'),
                collapse_host=body_host,
            )
        else:
            body = ctk.CTkFrame(body_host, fg_color='transparent')
            body.pack(fill='x', pady=(0, 24))

        self.stage_cards[stage_name] = {
            'frame': card,
            'badge': None,
            'title': title_label,
        }
        return body

    def _create_section_body(
        self,
        parent,
        section_name,
        toggle,
        expanded=False,
        pady=(0, 0),
        toggle_labels=('展开', '收起'),
        collapse_host=None,
    ):
        wrapper = ctk.CTkFrame(parent, fg_color='transparent')
        body = ctk.CTkFrame(wrapper, fg_color='transparent')
        body.pack(fill='x', expand=True)

        self.section_meta[section_name] = {
            'wrapper': wrapper,
            'toggle': toggle,
            'expanded': bool(expanded),
            'collapse_host': collapse_host,
            'pack_kwargs': {
                'fill': 'x',
                'pady': pady,
            },
            'toggle_labels': toggle_labels,
        }

        if expanded:
            wrapper.pack(**self.section_meta[section_name]['pack_kwargs'])

        self._sync_toggle_text(section_name)
        return body

    def _toggle_section(self, section_name, expanded=None, animate=True):
        _ = animate
        meta = self.section_meta.get(section_name)
        if not meta:
            return

        target = (not meta['expanded']) if expanded is None else bool(expanded)
        if target == meta['expanded']:
            return

        meta['expanded'] = target
        wrapper = meta['wrapper']
        collapse_host = meta.get('collapse_host')
        if target:
            if collapse_host is not None and collapse_host.winfo_exists():
                collapse_host.configure(height=1)
            wrapper.pack(**meta['pack_kwargs'])
        else:
            wrapper.pack_forget()
            if collapse_host is not None and collapse_host.winfo_exists():
                collapse_host.configure(height=0)

        self._sync_toggle_text(section_name)
        self._request_layout_pass(f'toggle-{section_name}', measure=True)

    def _sync_toggle_text(self, section_name):
        meta = self.section_meta.get(section_name)
        if not meta or not meta.get('toggle'):
            return
        collapsed_label, expanded_label = meta.get('toggle_labels', ('展开', '收起'))
        meta['toggle'].configure(text=expanded_label if meta['expanded'] else collapsed_label)

    def _set_stage_focus(self, stage_name, animate=True):
        self.active_stage = stage_name
        for name, widgets in self.stage_cards.items():
            is_active = name == stage_name
            frame = widgets['frame']
            badge = widgets['badge']
            title = widgets['title']
            border_target = self.COLORS['border_active'] if is_active else self.COLORS['border']
            badge_tone = 'brand' if is_active else 'neutral'
            title_color = self.COLORS['brand'] if is_active else self.COLORS['text_primary']

            self._animate_widget_option(
                key=f'stage-border-{name}',
                widget=frame,
                option='border_color',
                start_color=getattr(frame, '_current_border_color', self.COLORS['border']),
                end_color=border_target,
                animate=animate,
            )
            frame._current_border_color = border_target
            if badge is not None:
                self._set_badge_state(
                    badge,
                    self.STAGE_META[name][0],
                    tone=badge_tone,
                    animate=animate,
                )
            title.configure(text_color=title_color)

    def _run_startup_reveal(self):
        self._set_stage_focus(self.active_stage, animate=True)

    def _animate_slide_reveal(self, widget, final_pady, delay_ms=0, start_offset=18, duration_ms=None):
        _ = delay_ms, start_offset, duration_ms
        if widget.winfo_manager() == 'pack':
            widget.pack_configure(pady=final_pady)

    def _animate_widget_option(self, key, widget, option, start_color, end_color, animate=True):
        if not animate or self.is_sidebar_resizing:
            widget.configure(**{option: end_color})
            return
        self._animate_color(
            key=key,
            start_color=start_color,
            end_color=end_color,
            setter=lambda color: widget.configure(**{option: color}),
            duration_ms=self.COLOR_ANIMATION_MS,
        )

    def _build_textbox(self, parent, height, readonly=True):
        textbox = ctk.CTkTextbox(
            parent,
            height=height,
            corner_radius=16,
            border_width=1,
            border_color=self.COLORS['border'],
            fg_color=self.COLORS['panel_bg'],
            text_color=self.COLORS['text_primary'],
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=12),
            wrap='word',
        )
        textbox.configure(state='disabled' if readonly else 'normal')
        return textbox

    def _make_wrap_label(
        self,
        parent,
        *,
        text='',
        textvariable=None,
        text_color,
        font,
        padding=24,
        min_wrap=120,
        max_wrap=None,
        container=None,
    ):
        label = ctk.CTkLabel(
            parent,
            text=text,
            textvariable=textvariable,
            justify='left',
            anchor='w',
            text_color=text_color,
            font=font,
            wraplength=min_wrap,
        )
        self._register_wrap_label(label, container or parent, padding=padding, min_wrap=min_wrap, max_wrap=max_wrap)
        return label

    def _make_button(
        self,
        parent,
        label,
        command,
        *,
        width=None,
        height=38,
        state='normal',
        fg_color=None,
        hover_color=None,
        text_color=None,
    ):
        fg = fg_color or self.COLORS['brand']
        hover = hover_color or (self.COLORS['brand_hover'] if fg == self.COLORS['brand'] else self.COLORS['panel_alt'])
        kwargs = {
            'master': parent,
            'text': label,
            'command': command,
            'height': height,
            'corner_radius': 16,
            'state': state,
            'fg_color': fg,
            'hover_color': hover,
            'text_color': text_color or '#FFFFFF',
            'font': ctk.CTkFont(family='Microsoft YaHei UI', size=13, weight='bold'),
        }
        if width is not None:
            kwargs['width'] = width
        button = ctk.CTkButton(**kwargs)
        button._base_fg_color = fg
        button._base_hover_color = hover
        return button

    def _make_badge(self, parent, text, tone='neutral'):
        fg_color, text_color = self._tone_colors(tone)
        badge = ctk.CTkLabel(
            parent,
            text=text,
            corner_radius=999,
            fg_color=fg_color,
            text_color=text_color,
            padx=12,
            pady=5,
            font=ctk.CTkFont(family='Microsoft YaHei UI', size=11, weight='bold'),
        )
        badge._current_fg_color = fg_color
        badge._current_text_color = text_color
        return badge

    def _set_badge_state(self, badge, text, tone, animate=True):
        target_fg, target_text = self._tone_colors(tone)
        badge.configure(text=text)

        start_fg = getattr(badge, '_current_fg_color', target_fg)
        start_text = getattr(badge, '_current_text_color', target_text)
        if animate and not self.is_sidebar_resizing:
            self._animate_color(
                key=f'badge-fg-{id(badge)}',
                start_color=start_fg,
                end_color=target_fg,
                setter=lambda color: badge.configure(fg_color=color),
                duration_ms=self.COLOR_ANIMATION_MS,
            )
            self._animate_color(
                key=f'badge-text-{id(badge)}',
                start_color=start_text,
                end_color=target_text,
                setter=lambda color: badge.configure(text_color=color),
                duration_ms=self.COLOR_ANIMATION_MS,
            )
        else:
            badge.configure(fg_color=target_fg, text_color=target_text)

        badge._current_fg_color = target_fg
        badge._current_text_color = target_text

    def _set_splitter_state(self, state, animate=True):
        tone_map = {
            'idle': self.COLORS['splitter'],
            'hover': self.COLORS['splitter_hover'],
            'active': self.COLORS['splitter_active'],
        }
        target = tone_map.get(state, self.COLORS['splitter'])
        start = getattr(self.sidebar_resize_bar, '_current_fg_color', self.COLORS['splitter'])

        if animate and state != 'active' and not self.is_sidebar_resizing:
            self._animate_color(
                key='splitter-fg',
                start_color=start,
                end_color=target,
                setter=lambda color: self.sidebar_resize_bar.configure(fg_color=color),
                duration_ms=self.COLOR_ANIMATION_MS,
            )
        else:
            self.sidebar_resize_bar.configure(fg_color=target)

        self.sidebar_resize_bar._current_fg_color = target

    def _pulse_button(self, button):
        if str(button.cget('state')) == 'disabled' or self.is_sidebar_resizing:
            return

        base_color = getattr(button, '_base_fg_color', self.COLORS['brand'])
        pulse_color = '#4A83F3'

        def go_back():
            self._animate_color(
                key=f'button-pulse-return-{id(button)}',
                start_color=pulse_color,
                end_color=base_color,
                setter=lambda color: button.configure(fg_color=color),
                duration_ms=self.BUTTON_PULSE_MS,
            )

        self._animate_color(
            key=f'button-pulse-{id(button)}',
            start_color=base_color,
            end_color=pulse_color,
            setter=lambda color: button.configure(fg_color=color),
            duration_ms=self.BUTTON_PULSE_MS,
            on_complete=go_back,
        )

    def _tone_colors(self, tone):
        mapping = {
            'neutral': (self.COLORS['panel_bg'], self.COLORS['text_secondary']),
            'brand': (self.COLORS['brand_soft'], self.COLORS['brand']),
            'success': (self.COLORS['success_soft'], self.COLORS['success']),
            'warning': (self.COLORS['warning_soft'], self.COLORS['warning']),
            'danger': (self.COLORS['danger_soft'], self.COLORS['danger']),
        }
        return mapping.get(tone, mapping['neutral'])

    def _animate_value(self, key, start_value, end_value, duration_ms, setter, on_complete=None):
        token = self.animation_tokens.get(key, 0) + 1
        self.animation_tokens[key] = token
        steps = max(int(duration_ms / self.FRAME_MS), 1)

        def step(index):
            if self.animation_tokens.get(key) != token:
                return

            progress = self._ease_in_out_cubic(index / steps)
            current = start_value + (end_value - start_value) * progress
            setter(current)

            if index < steps:
                self.after(self.FRAME_MS, step, index + 1)
            else:
                setter(end_value)
                if on_complete:
                    on_complete()

        step(0)

    def _animate_color(self, key, start_color, end_color, setter, duration_ms=100, on_complete=None):
        start_rgb = self._hex_to_rgb(start_color)
        end_rgb = self._hex_to_rgb(end_color)

        def apply(progress):
            blended = tuple(
                int(start_rgb[index] + (end_rgb[index] - start_rgb[index]) * progress)
                for index in range(3)
            )
            setter(self._rgb_to_hex(blended))

        self._animate_value(
            key=key,
            start_value=0.0,
            end_value=1.0,
            duration_ms=duration_ms,
            setter=apply,
            on_complete=on_complete,
        )

    def _ease_in_out_cubic(self, value):
        value = max(0.0, min(1.0, float(value)))
        if value < 0.5:
            return 4 * value ** 3
        return 1 - ((-2 * value + 2) ** 3) / 2

    def _hex_to_rgb(self, value):
        value = str(value or '').strip().lstrip('#')
        if len(value) != 6:
            return 0, 0, 0
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    def _rgb_to_hex(self, rgb):
        red, green, blue = rgb
        return f'#{red:02X}{green:02X}{blue:02X}'

    def _schedule_ui_queue_pump(self, delay_ms):
        if self.ui_pump_after_id is not None:
            return
        self.ui_pump_after_id = self.after(delay_ms, self._drain_ui_queue)

    def _drain_ui_queue(self):
        self.ui_pump_after_id = None
        processed = 0
        limit = 64

        try:
            while processed < limit:
                item = self.ui_queue.get_nowait()
                processed += 1
                kind = item['kind']
                if kind == 'log':
                    self._append_log(item['level'], item['message'])
                elif kind == 'task_success':
                    self._complete_task(item)
                    if item.get('on_success'):
                        item['on_success'](item['result'])
                elif kind == 'task_error':
                    self._complete_task(item)
                    if item.get('on_error'):
                        item['on_error'](item['error'])
                    else:
                        self._handle_task_error(item['error'])
                elif kind == 'callback':
                    item['callback']()
        except queue.Empty:
            pass

        if not self.winfo_exists():
            return

        if processed and not self.ui_queue.empty():
            self._schedule_ui_queue_pump(self.UI_QUEUE_BUSY_MS)
        else:
            self._schedule_ui_queue_pump(self.UI_QUEUE_IDLE_MS)

    def _complete_task(self, item):
        self.busy_tasks.discard(item['task_key'])
        for widget in item.get('widgets', []):
            if widget.winfo_exists():
                widget.configure(state='normal')
        if item.get('on_finally'):
            item['on_finally']()

    def _run_task(self, task_key, widgets, target, on_success=None, on_error=None, on_finally=None, duplicate_message=None):
        if task_key in self.busy_tasks:
            self._append_log('warn', duplicate_message or '同类任务正在执行，请稍候。')
            return

        self.busy_tasks.add(task_key)
        for widget in widgets:
            if widget.winfo_exists():
                widget.configure(state='disabled')

        def worker():
            try:
                result = target()
            except Exception as exc:  # noqa: BLE001
                self.ui_queue.put({
                    'kind': 'task_error',
                    'task_key': task_key,
                    'widgets': widgets,
                    'error': exc,
                    'on_error': on_error,
                    'on_finally': on_finally,
                })
            else:
                self.ui_queue.put({
                    'kind': 'task_success',
                    'task_key': task_key,
                    'widgets': widgets,
                    'result': result,
                    'on_success': on_success,
                    'on_finally': on_finally,
                })

        threading.Thread(target=worker, daemon=True).start()

    def _notify_from_worker(self, level, message):
        self.ui_queue.put({'kind': 'log', 'level': level, 'message': message})

    def _append_log(self, level, message):
        if not hasattr(self, 'log_textbox') or not self.log_textbox.winfo_exists():
            return

        prefix = UI_STATUS_PREFIX.get(level, '[INFO]')
        line = f'{prefix} {message}\n'
        self.log_textbox.configure(state='normal')
        self.log_textbox.insert('end', line)
        self.log_textbox.see('end')
        self.log_textbox.configure(state='disabled')

        self.log_count += 1
        self.last_log_message = str(message).replace('\n', ' ').strip()
        preview = self.last_log_message
        if len(preview) > 28:
            preview = preview[:28] + '...'
        self.log_summary_var.set(f'共 {self.log_count} 条日志，最近：{preview or "暂无"}')
        self._sync_log_visibility(level)
        self._request_layout_pass('log-append')

    def _sync_log_visibility(self, level):
        if level in {'warn', 'error'}:
            self._toggle_section('log', True)

    def _clear_logs(self):
        self._set_textbox(self.log_textbox, '')
        self.log_count = 0
        self.last_log_message = ''
        self.log_summary_var.set('日志已清空。')
        self._append_log('info', '日志已清空。')

    def _set_textbox(self, textbox, value):
        original_state = str(textbox._textbox.cget('state'))
        textbox.configure(state='normal')
        textbox.delete('1.0', 'end')
        if value:
            textbox.insert('1.0', value)
        textbox.configure(state=original_state)

    def _read_textbox(self, textbox):
        return textbox.get('1.0', 'end').strip()

    def _selected_browser(self):
        return self.BROWSER_SEGMENTS[self.browser_segment_var.get()]

    def _selected_ai_mode(self):
        return self.AI_SEGMENTS[self.ai_segment_var.get()]

    def _refresh_config_summary(self):
        address = self.address_entry.get().strip()
        cookie = self._read_textbox(self.cookie_textbox)
        api_key = self.api_entry.get().strip()

        host = urlparse(address).netloc.strip() if address else ''
        address_text = host or ('已填写地址' if address else '未配置')
        cookie_text = f'已配置 {len(cookie)} 字符' if cookie else '未配置'
        api_text = '已配置' if api_key else '未配置'
        self.config_summary_var.set(
            f'地址：{address_text}\nCookie：{cookie_text}\nAPI：{api_text}'
        )
        self._request_layout_pass('config-summary')

    def _load_config_into_form(self):
        config = load_config_values()
        self.address_entry.delete(0, 'end')
        self.address_entry.insert(0, config.get('address', ''))
        self._set_textbox(self.cookie_textbox, config.get('cookie', ''))
        self.api_entry.delete(0, 'end')
        self.api_entry.insert(0, config.get('api_key', ''))
        self._refresh_config_summary()
        self._append_log('info', '已从配置文件加载地址、Cookie 和 API Key。')

    def _save_config(self):
        config = save_config_values(
            address=self.address_entry.get().strip(),
            cookie=self._read_textbox(self.cookie_textbox),
            api_key=self.api_entry.get().strip(),
        )
        self.address_entry.delete(0, 'end')
        self.address_entry.insert(0, config.get('address', ''))
        self._set_textbox(self.cookie_textbox, config.get('cookie', ''))
        self.api_entry.delete(0, 'end')
        self.api_entry.insert(0, config.get('api_key', ''))
        self._refresh_config_summary()
        self._append_log('success', '配置已保存。')
        messagebox.showinfo('保存成功', '地址、Cookie 和 API Key 已保存。')

    def _choose_driver_directory(self):
        path = filedialog.askdirectory(title='选择浏览器驱动目录')
        if not path:
            return
        self.driver_path_var.set(path)
        self._refresh_driver_status()

    def _clear_driver_directory(self):
        self.driver_path_var.set('')
        self._refresh_driver_status()

    def _refresh_driver_status(self, show_log=True):
        status = get_driver_status(custom_path=self.driver_path_var.get())
        available = status.get('available', [])
        missing = status.get('missing', [])
        custom_path = status.get('custom_path', '')

        tone = 'success' if available else 'warning'
        badge_text = '驱动可用' if available else '缺少驱动'
        self._set_badge_state(self.driver_badge, badge_text, tone=tone, animate=True)

        if custom_path:
            self.driver_summary_var.set(f'当前自定义目录：{custom_path}')
        else:
            self.driver_summary_var.set('当前使用程序目录或 EXE 同级目录检测驱动。')

        self.driver_available_var.set(
            '可用驱动：' + ('、'.join(name.upper() for name in available) if available else '无')
        )
        self.driver_missing_var.set(
            '缺失驱动：' + ('、'.join(name.upper() for name in missing) if missing else '无')
        )

        self._request_layout_pass('driver-status')

        if show_log:
            if available:
                self._append_log('success', f"检测到可用驱动：{', '.join(available)}")
            else:
                self._append_log('warn', '未检测到可用驱动，请确认驱动文件或目录设置。')

    def _set_login_state(self, text, tone='neutral'):
        self.login_status_var.set(text)
        badge_text = text if len(text) <= 10 else text[:10] + '...'
        self._set_badge_state(self.login_badge, badge_text, tone=tone)
        self._request_layout_pass('login-state')

    def _start_login_flow(self):
        if self.current_login_controller is not None:
            self._append_log('warn', '登录流程已经在等待中。')
            return

        self.current_login_controller = LoginWaitController()
        self.check_login_button.configure(state='normal')
        self.cancel_login_button.configure(state='normal')
        browser_label = BROWSER_LABELS[self._selected_browser()]
        self._set_login_state(f'等待登录 · {browser_label}', tone='brand')
        self._append_log('info', f'准备使用 {browser_label} 获取 Cookie。')

        browser_type = self._selected_browser()

        def target():
            return run_manual_login(
                browser_type=browser_type,
                notify=self._notify_from_worker,
                wait_controller=self.current_login_controller,
            )

        def on_success(result):
            cookie_value = result.get('cookie', '')
            self._set_textbox(self.cookie_textbox, cookie_value)
            self._refresh_config_summary()
            self._set_login_state('登录成功', tone='success')
            self._append_log('success', 'Cookie 已回写到配置区。')
            messagebox.showinfo('登录成功', 'Cookie 获取成功，已同步到配置区并写入文件。')

        def on_error(error):
            message = str(error)
            if '登录已取消' in message:
                self._set_login_state('已取消', tone='warning')
                self._append_log('warn', message)
                return
            self._set_login_state('登录失败', tone='danger')
            self._handle_task_error(error)

        def on_finally():
            self.current_login_controller = None
            self.check_login_button.configure(state='disabled')
            self.cancel_login_button.configure(state='disabled')

        self._run_task(
            'login',
            [self.start_login_button, self.browser_segment],
            target,
            on_success=on_success,
            on_error=on_error,
            on_finally=on_finally,
            duplicate_message='登录流程正在进行中，请先完成或取消。',
        )

    def _request_login_check(self):
        if self.current_login_controller is None:
            self._append_log('warn', '当前没有正在等待的登录流程。')
            return
        self.current_login_controller.request_check()
        self._set_login_state('正在检查登录状态', tone='brand')
        self._append_log('info', '已请求检查当前浏览器登录状态。')

    def _cancel_login_flow(self):
        if self.current_login_controller is None:
            self._append_log('warn', '当前没有正在等待的登录流程。')
            return
        self.current_login_controller.cancel()
        self._set_login_state('正在取消', tone='warning')
        self._append_log('warn', '已请求取消登录流程。')

    def _start_solve_flow(self):
        address = self.address_entry.get().strip()
        cookie = self._read_textbox(self.cookie_textbox)
        api_key = self.api_entry.get().strip()
        ai_mode = self._selected_ai_mode()

        self.last_solution = None
        self.qa_context = None
        self._set_stage_focus('solve')
        self._toggle_section('result', True)
        self._toggle_section('qa', False)
        self.autofill_button.configure(state='disabled')
        self.ask_button.configure(state='disabled')
        self.question_count_var.set('题目数量：-')
        self.question_types_var.set('题型覆盖：-')
        self.result_summary_var.set('结构化结果：正在抓取题目并生成答案')
        self.autofill_summary_var.set('自动填写：等待新的解题结果')
        self._set_badge_state(self.result_badge, '正在生成', tone='brand')
        self._set_textbox(self.raw_result_textbox, '正在抓取题目并请求 AI，请稍候...')
        self._set_textbox(self.structured_result_textbox, '等待结构化解析...')
        self._set_textbox(self.qa_answer_textbox, '')
        self._request_layout_pass('solve-start', measure=True)

        def target():
            return solve_homework(
                address=address,
                cookie=cookie,
                api_key=api_key,
                ai_mode=ai_mode,
                notify=self._notify_from_worker,
                browser_type=self._selected_browser(),
            )

        def on_success(result):
            self.last_solution = result
            self.qa_context = result.get('qa_context')
            summary = result.get('question_summary', {})
            self.question_count_var.set(f"题目数量：{summary.get('count', '-')}")
            self.question_types_var.set(f"题型覆盖：{summary.get('type_summary', '-')}")
            self._set_textbox(self.raw_result_textbox, result.get('raw_result', ''))

            structured_answer = result.get('structured_answer')
            if structured_answer:
                self.result_summary_var.set(
                    f"结构化结果：已成功解析 {len(structured_answer.get('answers', []))} 题"
                )
                self._set_textbox(
                    self.structured_result_textbox,
                    structured_answer.get('json_text', ''),
                )
                self._set_badge_state(self.result_badge, '结构化成功', tone='success')
                self.autofill_button.configure(state='normal')
                self._pulse_button(self.autofill_button)
            else:
                self.result_summary_var.set('结构化结果：解析失败，当前仅可查看原始 AI 输出')
                self._set_textbox(
                    self.structured_result_textbox,
                    result.get('structured_error', '结构化答案解析失败。'),
                )
                self._set_badge_state(self.result_badge, '仅原始结果', tone='warning')
                self.autofill_button.configure(state='disabled')

            self.autofill_summary_var.set('自动填写：等待你确认后再执行')
            self.ask_button.configure(state='normal' if self.qa_context else 'disabled')
            self._toggle_section('qa', True)
            self._set_stage_focus('result')
            self._append_log('success', '作业解答已完成。')
            self._request_layout_pass('solve-success', measure=True)

        def on_error(error):
            self.result_summary_var.set('结构化结果：解题失败')
            self.autofill_summary_var.set('自动填写：本次未执行')
            self._set_badge_state(self.result_badge, '解题失败', tone='danger')
            self._set_textbox(self.structured_result_textbox, str(error))
            self._toggle_section('result', True)
            self._toggle_section('qa', False)
            self._set_stage_focus('result')
            self._request_layout_pass('solve-error', measure=True)
            self._handle_task_error(error)

        self._run_task(
            'solve',
            [self.solve_button],
            target,
            on_success=on_success,
            on_error=on_error,
            duplicate_message='解题任务正在执行，请稍候。',
        )

    def _start_autofill_flow(self):
        if not self.last_solution or not self.last_solution.get('structured_answer'):
            self._append_log('warn', '当前没有可自动填写的结构化答案。')
            return

        address = self.address_entry.get().strip()
        cookie = self._read_textbox(self.cookie_textbox)
        structured_answer = self.last_solution['structured_answer']
        browser_type = self._selected_browser()
        self.autofill_summary_var.set('自动填写：正在回填网页，请稍候')
        self._set_stage_focus('result')
        self._request_layout_pass('autofill-start')

        def target():
            return run_autofill(
                address=address,
                cookie=cookie,
                structured_answer=structured_answer,
                browser_type=browser_type,
                notify=self._notify_from_worker,
            )

        def on_success(report):
            success_count = len(report.get('success', []))
            failure_count = len(report.get('failure', []))
            skipped_count = len(report.get('skipped', []))
            auto_submitted = bool(report.get('auto_submitted'))
            self.autofill_summary_var.set(
                f'自动填写：成功 {success_count}，失败 {failure_count}，跳过 {skipped_count}'
            )
            self._set_badge_state(self.result_badge, '填写完成', tone='success')
            if auto_submitted:
                self._append_log('success', '当前页面识别为章节测验，程序已在填写完成后自动提交。')
            else:
                self._append_log('info', '浏览器会保留在作业页，程序不会自动提交。')
            self._request_layout_pass('autofill-success', measure=True)
            if auto_submitted:
                messagebox.showinfo(
                    '自动填写完成',
                    f'成功 {success_count} 题，失败 {failure_count} 题，跳过 {skipped_count} 题。\n当前页面识别为章节测验，程序已自动提交。',
                )
            else:
                messagebox.showinfo(
                    '自动填写完成',
                    f'成功 {success_count} 题，失败 {failure_count} 题，跳过 {skipped_count} 题。\n浏览器已保留在作业页，请人工检查后再决定是否提交。',
                )

        def on_error(error):
            self.autofill_summary_var.set('自动填写：执行失败')
            self._set_badge_state(self.result_badge, '填写失败', tone='warning')
            self._request_layout_pass('autofill-error', measure=True)
            self._handle_task_error(error)

        self._run_task(
            'autofill',
            [self.autofill_button],
            target,
            on_success=on_success,
            on_error=on_error,
            duplicate_message='自动填写正在执行，请稍候。',
        )

    def _start_followup_flow(self):
        if not self.qa_context:
            self._append_log('warn', '请先完成一次作业解答，再继续追问。')
            return

        question = self.qa_entry.get().strip()
        if not question:
            self._append_log('warn', '请输入要追问的问题。')
            return

        self._toggle_section('qa', True)
        self._set_stage_focus('qa')

        def target():
            return ask_followup(
                qa_context=self.qa_context,
                question=question,
                notify=self._notify_from_worker,
            )

        def on_success(result):
            self.qa_context = result.get('qa_context')
            self._set_textbox(self.qa_answer_textbox, result.get('answer', ''))
            self.qa_entry.delete(0, 'end')
            self._set_stage_focus('qa')
            self._append_log('success', '追问回答已返回。')
            self._request_layout_pass('followup-success', measure=True)

        self._run_task(
            'followup',
            [self.ask_button],
            target,
            on_success=on_success,
            duplicate_message='上一条追问还在处理中，请稍候。',
        )

    def _handle_task_error(self, error):
        message = str(error)
        self._append_log('error', message)
        messagebox.showerror('任务失败', message)

    def _inline_button_pad(self, index, total):
        if total <= 1:
            return 0
        if index == 0:
            return (0, 4)
        if index == total - 1:
            return (4, 0)
        return 4

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _on_close(self):
        if self.current_login_controller is not None:
            try:
                self.current_login_controller.cancel()
            except Exception:
                pass
            self.current_login_controller = None
        for controller in list(self.parallel_controllers):
            try:
                controller.request_stop()
            except Exception:
                continue
        if self.ui_pump_after_id is not None:
            self.after_cancel(self.ui_pump_after_id)
            self.ui_pump_after_id = None
        if self.layout_after_id is not None:
            self.after_cancel(self.layout_after_id)
            self.layout_after_id = None
        if self.scroll_sync_after_id is not None:
            self.after_cancel(self.scroll_sync_after_id)
            self.scroll_sync_after_id = None
        self.destroy()


def main():
    ctk.set_appearance_mode('light')
    app = MoocRobotGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
