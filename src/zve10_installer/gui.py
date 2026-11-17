"""Five-step guided GUI.

The main window only shows what the user needs: preparation, checks, flashing,
cold boot, and acceptance. Technical tools and logs live behind the
"技术详情/高级" button. The install and WBI sessions are the same engines used by
the CLI.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__, doctor, history, paths, selfcheck
from .errors import InstallerError
from .platform_compat import is_read_only_build, repo_root
from .steps import diagnostics
from .steps import inspect as inspect_step
from .steps import install_session as install_session_module
from .steps import verify as verify_step
from .steps import wbi as wbi_step
from .upstream import Upstream, locate

BG = "#F1F5F9"
CARD = "#FFFFFF"
OUTPUT_BG = "#F8FAFC"
TEXT = "#0F172A"
MUTED = "#64748B"
BORDER = "#E2E8F0"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
SECONDARY = "#E2E8F0"
SECONDARY_HOVER = "#CBD5E1"
OK = "#059669"
WARN = "#D97706"
DANGER = "#DC2626"

FONT = "Microsoft YaHei UI"
MONO = "Cascadia Mono"


class InstallerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title("ZV-E10 5GHz Installer")
        self.geometry("920x800")
        self.minsize(860, 740)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.upstream: Upstream | None = None
        self.runs_dir = paths.default_runs_dir()
        self.install = None
        self.install_facts: dict = {}
        self.wbi = None
        self.wbi_tool: Path | None = None
        self.wbi_prepared: dict | None = None
        self.wbi_attempted = False
        self.verify_result: dict | None = None

        self.step = 1
        self._busy = False
        self.pre_checks: dict = {}
        self.region_confirmed = False
        self.battery_confirmed = False
        self.recovery_confirmed = False
        self.log_lines: list[str] = []
        self.log_path: Path | None = None
        try:
            paths.ensure_data_dir()
            logs = paths.logs_dir()
            logs.mkdir(parents=True, exist_ok=True)
            self.log_path = logs / f"gui-{datetime.now():%Y%m%d-%H%M%S}.log"
            self.log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
        self.tech_window = None
        self.action_buttons: list[ctk.CTkButton] = []

        self._build_shell()
        self._show_step(1)
        self.after(150, self._init_upstream)

    # -- shell -------------------------------------------------------------
    def _font(self, size: int = 13, bold: bool = False) -> ctk.CTkFont:
        return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent, corner_radius=16, fg_color=CARD, border_width=1, border_color=BORDER
        )

    def _build_shell(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(22, 4))
        ctk.CTkLabel(
            header, text="ZV-E10 5GHz Installer", font=self._font(26, True), text_color=TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=f"v{__version__}  ·  5 步完成  ·  先检查条件，再允许刷入",
            font=self._font(12),
            text_color=MUTED,
        ).pack(anchor="w", pady=(2, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=28, pady=(8, 8))
        self.step_labels: list[ctk.CTkLabel] = []
        for number, title in enumerate(
            ("准备", "检查", "刷入", "冷启动", "验收"), start=1
        ):
            label = ctk.CTkLabel(
                bar,
                text=f"{number} {title}",
                font=self._font(12, True),
                text_color=MUTED,
            )
            label.pack(side="left", padx=(0, 18))
            self.step_labels.append(label)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=28, pady=(0, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=28, pady=(0, 18))
        ctk.CTkButton(
            footer,
            text="技术详情 / 高级",
            width=140,
            height=34,
            corner_radius=10,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(12),
            command=self._open_tech,
        ).pack(side="left")
        self.status = ctk.CTkLabel(
            footer, text="", font=self._font(11), text_color=MUTED
        )
        self.status.pack(side="left", padx=12)
        ctk.CTkButton(
            footer,
            text="退出",
            width=90,
            height=34,
            corner_radius=10,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(12),
            command=self._on_close,
        ).pack(side="right")

    def _update_step_bar(self) -> None:
        for index, label in enumerate(self.step_labels, start=1):
            if index < self.step:
                color, text_color = OK, OK
            elif index == self.step:
                color, text_color = ACCENT, ACCENT
            else:
                color, text_color = MUTED, MUTED
            label.configure(text_color=text_color)

    def _show_step(self, step: int, **kwargs) -> None:
        self.step = step
        self._update_step_bar()
        for child in self.content.winfo_children():
            child.destroy()
        self.action_buttons = []
        if step == 1:
            self._build_step_1()
        elif step == 2:
            self._build_step_2(**kwargs)
        elif step == 3:
            self._build_step_3(**kwargs)
        elif step == 4:
            self._build_step_4(**kwargs)
        elif step == 5:
            self._build_step_5(**kwargs)

    # -- startup -----------------------------------------------------------
    def _init_upstream(self) -> None:
        try:
            paths.ensure_data_dir()
        except OSError as exc:
            messagebox.showerror(
                "备份目录不可写",
                "请将程序解压到可写目录（例如桌面或文档），不要直接在 zip 内运行。\n\n"
                + str(exc),
            )
            self.status.configure(text="备份目录不可写", text_color=DANGER)
            return
        try:
            self.upstream = locate(None)
        except InstallerError as exc:
            self.status.configure(text=f"上游未找到：{exc}", text_color=DANGER)
            self._log(f"错误: {exc}")
            return
        self._log(f"上游: {self.upstream.root}")
        self._log(f"备份目录: {paths.data_dir()}")
        if self.log_path is not None:
            self._log(f"日志文件: {self.log_path}")
        if self.step == 1:
            self._refresh_preconditions()

    # -- step 1: preparation ----------------------------------------------
    def _build_step_1(self) -> None:
        card = self._card(self.content)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            card, text="第 1 步 · 准备", font=self._font(20, True), text_color=TEXT
        ).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(
            card,
            text="确认下面的条件。程序会自动检查相机并做整盘备份。",
            font=self._font(12),
            text_color=MUTED,
        ).pack(anchor="w", padx=24, pady=(0, 12))

        table = ctk.CTkFrame(card, fg_color="transparent")
        table.pack(fill="x", padx=24)
        table.grid_columnconfigure(1, weight=1)
        self.pc_status: dict[str, ctk.CTkLabel] = {}

        def row(index: int, name: str, value: str, key: str | None = None, color: str = MUTED):
            ctk.CTkLabel(
                table,
                text=name,
                width=90,
                anchor="w",
                font=self._font(13, True),
                text_color=TEXT,
            ).grid(row=index, column=0, sticky="w", pady=5)
            label = ctk.CTkLabel(
                table,
                text=value,
                anchor="w",
                font=self._font(12),
                text_color=color,
            )
            label.grid(row=index, column=1, sticky="w", pady=5)
            if key:
                self.pc_status[key] = label
            return label

        row(0, "相机", "ZV-E10 一代")
        row(1, "固件", "2.02 / 2.03（检查时自动读取）")
        row(2, "USB 模式", "检测中…", "mode")
        row(3, "驱动", "检测中…", "driver")
        self.driver_button = ctk.CTkButton(
            table,
            text="安装驱动",
            width=96,
            height=28,
            corner_radius=8,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(11, True),
            command=self._install_driver,
            state="disabled",
        )
        self.driver_button.grid(row=3, column=2, padx=8)
        self.driver_recovery_button = ctk.CTkButton(
            table,
            text="驱动恢复",
            width=96,
            height=28,
            corner_radius=8,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(11, True),
            command=self._recover_driver,
            state="disabled",
        )
        self.driver_recovery_button.grid(row=3, column=3, padx=(0, 8))
        row(4, "连接", "检测中…", "camera")
        row(5, "备份位置", f"{paths.data_dir()}（自动）", "backup")

        confirms = ctk.CTkFrame(card, fg_color="transparent")
        confirms.pack(fill="x", padx=24, pady=(14, 4))
        self.region_var = tk.BooleanVar(value=self.region_confirmed)
        ctk.CTkCheckBox(
            confirms,
            text="相机将在中国大陆使用（B=2 / C=22）",
            variable=self.region_var,
            font=self._font(12),
            checkbox_width=20,
            checkbox_height=20,
            command=self._on_confirm_change,
        ).pack(anchor="w", pady=3)

        self.battery_var = tk.BooleanVar(value=self.battery_confirmed)
        ctk.CTkCheckBox(
            confirms,
            text="我已确认相机电量 ≥75%，写入期间不会断电",
            variable=self.battery_var,
            font=self._font(12),
            checkbox_width=20,
            checkbox_height=20,
            command=self._on_battery_change,
        ).pack(anchor="w", pady=3)

        ctk.CTkLabel(
            card,
            text=(
                "检查会先做约 2 分钟只读稳定性测试，再整盘备份（约 15 分钟）"
                "并自动复制第二份到程序目录的 backup/。两份备份位于同一磁盘，"
                "重要操作后建议再复制到其他磁盘。期间不要断开相机、不要关机。"
                "每次新的检查或刷入前请先冷启动相机。"
            ),
            font=self._font(11),
            text_color=WARN,
            wraplength=820,
            justify="left",
        ).pack(anchor="w", padx=24, pady=(10, 6))

        last_run = history.latest(self.runs_dir)
        if last_run and last_run.get("unfinished"):
            ctk.CTkLabel(
                card,
                text=(
                    f"⚠️ 上次运行：{last_run['label']}\n"
                    f"{last_run.get('error') or ''}\n"
                    "请在“技术详情 / 高级”里复核，不要盲目重试写入。"
                ),
                font=self._font(11, True),
                text_color=DANGER,
                wraplength=820,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(0, 6))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(4, 18))
        self.redetect_button = ctk.CTkButton(
            buttons,
            text="重新检测",
            width=110,
            height=38,
            corner_radius=10,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(12, True),
            command=self._refresh_preconditions,
        )
        self.redetect_button.pack(side="left")
        self.start_check_button = ctk.CTkButton(
            buttons,
            text="开始检查",
            width=140,
            height=38,
            corner_radius=10,
            fg_color="#CBD5E1",
            hover_color=ACCENT_HOVER,
            text_color=TEXT,
            font=self._font(13, True),
            command=self._start_check,
            state="disabled",
        )
        self.start_check_button.pack(side="left", padx=10)
        self.action_buttons = [self.redetect_button]
        self._refresh_preconditions()

    def _on_confirm_change(self) -> None:
        self.region_confirmed = bool(self.region_var.get())
        self._update_start_check()

    def _on_battery_change(self) -> None:
        self.battery_confirmed = bool(self.battery_var.get())
        self._update_start_check()

    def _refresh_preconditions(self) -> None:
        if self.upstream is None or self._busy:
            return
        status = getattr(self, "pc_status", {})
        for key in ("camera", "mode", "driver"):
            if key in status:
                status[key].configure(text="检测中…", text_color=WARN)
        self._log("检测相机与驱动…")

        def worker() -> None:
            checks = doctor.run(self.upstream)
            self.after(0, lambda: self._apply_preconditions(checks))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_preconditions(self, checks) -> None:
        self.pre_checks = {check.name: check for check in checks}
        status = getattr(self, "pc_status", {})
        camera = self.pre_checks.get("camera_usb")
        mode = self.pre_checks.get("mass_storage")
        driver = self.pre_checks.get("winusb_open")
        if "camera" in status:
            if camera and camera.ok:
                status["camera"].configure(text=f"已连接 {camera.detail}", text_color=OK)
            else:
                status["camera"].configure(text="未连接", text_color=DANGER)
        if "mode" in status:
            if mode and mode.ok:
                status["mode"].configure(text="Mass Storage", text_color=OK)
            elif camera and camera.ok:
                status["mode"].configure(
                    text="请把相机的 USB 连接改为 Mass Storage", text_color=DANGER
                )
            else:
                status["mode"].configure(text="先连接相机", text_color=MUTED)
        if "driver" in status:
            if driver and driver.ok:
                status["driver"].configure(text="WinUSB 已绑定", text_color=OK)
            elif camera and camera.ok:
                status["driver"].configure(text="未绑定", text_color=DANGER)
            else:
                status["driver"].configure(text="先连接相机", text_color=MUTED)
        if hasattr(self, "driver_button"):
            enabled = bool(driver and not driver.ok) and not is_read_only_build()
            self.driver_button.configure(state="normal" if enabled else "disabled")
        if hasattr(self, "driver_recovery_button"):
            self.driver_recovery_button.configure(
                state="normal" if (camera and camera.ok) else "disabled"
            )
        self._update_start_check()

    def _update_start_check(self) -> None:
        if not hasattr(self, "start_check_button"):
            return
        ready = all(
            self.pre_checks.get(name) is not None and self.pre_checks[name].ok
            for name in ("camera_usb", "mass_storage", "winusb_open")
        )
        region_ok = bool(self.region_var.get()) if hasattr(self, "region_var") else self.region_confirmed
        battery_ok = bool(self.battery_var.get()) if hasattr(self, "battery_var") else self.battery_confirmed
        ready = (
            ready
            and region_ok
            and battery_ok
            and not self._busy
            and not is_read_only_build()
        )
        self.start_check_button.configure(
            state="normal" if ready else "disabled",
            fg_color=ACCENT if ready else "#CBD5E1",
            text_color="#FFFFFF" if ready else TEXT,
        )

    def _install_driver(self) -> None:
        self._log("用户操作：打开驱动助手")
        zadig = repo_root() / "vendor" / "zadig" / "zadig-2.9.exe"
        if not zadig.is_file():
            messagebox.showerror("驱动助手缺失", f"找不到内置驱动助手：\n{zadig}")
            return
        messagebox.showinfo(
            "安装 WinUSB 驱动",
            "1. 在弹出的 Zadig 中选择 ZV-E10（054c:0d95）。\n"
            "2. Driver 选择 WinUSB。\n"
            "3. 点击 Install Driver 或 Replace Driver。\n"
            "4. 完成并关闭 Zadig，回到本程序点“重新检测”。\n\n"
            "Zadig 是独立程序，安装驱动可能需要管理员权限。",
        )
        try:
            subprocess.Popen([str(zadig)])
        except OSError as exc:
            messagebox.showerror("无法启动驱动助手", str(exc))

    def _recover_driver(self) -> None:
        self._log("用户操作：打开驱动恢复")
        proceed = messagebox.askyesno(
            "恢复 Windows 默认驱动",
            "将打开设备管理器。\n\n"
            "1. 找到 ZV-E10（或 Sony USB Device）\n"
            "2. 右键 → 卸载设备\n"
            "3. 勾选“删除此设备的驱动程序软件”\n"
            "4. 拔掉 USB，重新以 Mass Storage 插上\n"
            "5. 回到本程序点“重新检测”\n\n"
            "只卸载相机设备，不要卸载键盘、鼠标等其他设备。继续？",
        )
        if not proceed:
            return
        try:
            os.startfile("devmgmt.msc")
        except OSError as exc:
            try:
                subprocess.Popen(["mmc", "devmgmt.msc"])
            except OSError as second:
                messagebox.showerror("无法打开设备管理器", f"{exc}\n{second}")

    def _start_check(self) -> None:
        if self.upstream is None or self._busy:
            return
        self.region_confirmed = bool(self.region_var.get())
        self.battery_confirmed = bool(self.battery_var.get())
        if not (self.region_confirmed and self.battery_confirmed):
            return
        self._show_step(2, progress=True)
        self._log("用户操作：开始检查与备份")

        def prepare():
            session = install_session_module.InstallSession(
                self.upstream,
                self.runs_dir,
                battery_confirmed=self.battery_confirmed,
            )
            try:
                facts = session.prepare("CN-B2C22")
            except Exception:
                session.close()
                raise
            return {"session": session, "facts": facts}

        self._run_task("检查并备份", prepare, self._check_done)

    def _build_step_2(self, facts=None, error=None, progress=False) -> None:
        card = self._card(self.content)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            card, text="第 2 步 · 检查", font=self._font(20, True), text_color=TEXT
        ).pack(anchor="w", padx=24, pady=(18, 2))
        if progress:
            ctk.CTkLabel(
                card,
                text=(
                    "正在做连接稳定性测试（约 2 分钟）、整盘备份（约 15 分钟）"
                    "并复制第二份备份…\n请不要断开相机或关机。"
                ),
                font=self._font(14, True),
                text_color=WARN,
                justify="left",
            ).pack(anchor="w", padx=24, pady=18)
            return
        if error is not None:
            ctk.CTkLabel(
                card,
                text=f"❌ 不满足刷入条件\n{self._friendly_error(error)}",
                font=self._font(14, True),
                text_color=DANGER,
                justify="left",
                wraplength=800,
            ).pack(anchor="w", padx=24, pady=(10, 16))
            button = ctk.CTkButton(
                card,
                text="返回第 1 步",
                width=130,
                height=38,
                corner_radius=10,
                fg_color=SECONDARY,
                hover_color=SECONDARY_HOVER,
                text_color=TEXT,
                font=self._font(12, True),
                command=self._back_to_prepare,
            )
            button.pack(anchor="w", padx=24, pady=(0, 18))
            self.action_buttons = [button]
            return

        lines = self._checklist_lines(facts or {})
        ctk.CTkLabel(
            card,
            text="✅ 检查通过",
            font=self._font(16, True),
            text_color=OK,
        ).pack(anchor="w", padx=24, pady=(10, 6))
        ctk.CTkLabel(
            card,
            text="\n".join(lines),
            font=self._font(12),
            text_color=TEXT,
            justify="left",
            wraplength=800,
        ).pack(anchor="w", padx=24, pady=(0, 16))
        button = ctk.CTkButton(
            card,
            text="下一步：刷入",
            width=160,
            height=40,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self._font(13, True),
            command=lambda: self._show_step(3),
        )
        button.pack(anchor="w", padx=24, pady=(0, 18))
        self.action_buttons = [button]

    def _checklist_lines(self, facts: dict) -> list[str]:
        props = facts.get("backup") or {}
        stability = facts.get("stability") or {}
        return [
            "✅ 相机连接与认证",
            f"✅ 固件 {facts.get('firmware')}",
            "✅ 系统文件与区域属性未修改",
            "✅ /usr 分区为只读",
            f"✅ 连接稳定性：{stability.get('passes')} 次读取一致",
            "✅ 电量：已确认 ≥75%",
            f"✅ 机身 ID：{facts.get('body_id')}",
            f"✅ 整盘备份完成：{facts.get('backup_dir')}",
            f"✅ 第二份备份：{facts.get('backup_copy')}（程序目录）",
            f"✅ 地区确认：{facts.get('region')}",
            f"（属性 {props.get('0x1071c54')}/{props.get('0xa5000b')}/{props.get('0xa5000c')}）",
        ]

    def _back_to_prepare(self) -> None:
        if self.install is not None:
            self._log("关闭未完成的刷入会话")
            self.install.close()
            self.install = None
        self._show_step(1)

    # -- step 3: write -----------------------------------------------------
    def _build_step_3(self, progress=False, error=None) -> None:
        card = self._card(self.content)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            card, text="第 3 步 · 刷入", font=self._font(20, True), text_color=TEXT
        ).pack(anchor="w", padx=24, pady=(18, 2))
        if progress:
            ctk.CTkLabel(
                card,
                text="正在写入补丁和属性…\n不要断电、不要拔线。",
                font=self._font(14, True),
                text_color=WARN,
                justify="left",
            ).pack(anchor="w", padx=24, pady=18)
            return
        if error is not None:
            ctk.CTkLabel(
                card,
                text=f"❌ 写入失败\n{error}\n\n请保留证据，不要重复刷入。",
                font=self._font(14, True),
                text_color=DANGER,
                justify="left",
                wraplength=800,
            ).pack(anchor="w", padx=24, pady=(10, 18))
            return
        ctk.CTkLabel(
            card,
            text=(
                "即将写入：\n"
                "  · /usr/lib/CautionConfig.so 的单字节补丁\n"
                "  · 三个 Backup 属性（01 / 02 / 16）\n\n"
                "这是本次操作里唯一会修改相机的步骤。"
            ),
            font=self._font(13),
            text_color=TEXT,
            justify="left",
        ).pack(anchor="w", padx=24, pady=(8, 16))
        button = ctk.CTkButton(
            card,
            text="开始刷入",
            width=160,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self._font(14, True),
            command=self._do_install,
        )
        button.pack(anchor="w", padx=24, pady=(0, 18))
        self.action_buttons = [button]

    def _do_install(self) -> None:
        if self.install is None or self._busy:
            return
        self._log("用户操作：请求开始刷入")
        answer = ctk.CTkInputDialog(
            text="输入 PATCH ZV-E10 2.03 以确认写入。",
            title="写入确认",
        ).get_input()
        if answer is None or answer.strip() != "PATCH ZV-E10 2.03":
            self._log("写入确认不匹配，未写入。")
            return
        self._show_step(3, progress=True)
        self._run_task("刷入", self.install.execute, self._install_done)

    def _install_done(self, result, error) -> None:
        if error is not None:
            self._show_step(3, error=str(error))
            self.install = None
            return
        self.install = None
        self._show_step(4, wbi_done=False)

    # -- step 4: cold boot -------------------------------------------------
    def _build_step_4(self, wbi_done=False, progress=False, error=None) -> None:
        card = self._card(self.content)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            card, text="第 4 步 · 冷启动", font=self._font(20, True), text_color=TEXT
        ).pack(anchor="w", padx=24, pady=(18, 2))
        if wbi_done:
            ctk.CTkLabel(
                card,
                text="WBI 写入完成。请再次冷启动相机，然后继续验收。",
                font=self._font(13, True),
                text_color=OK,
            ).pack(anchor="w", padx=24, pady=(0, 8))
        ctk.CTkLabel(
            card,
            text=(
                "请按顺序操作：\n"
                "  1. 关机，等存取指示灯熄灭\n"
                "  2. 拔掉 USB 线\n"
                "  3. 取出电池，等约 30 秒\n"
                "  4. 装回电池，开机\n"
                "  5. USB 连接设为 Mass Storage\n"
                "  6. 插回 USB 线"
            ),
            font=self._font(13),
            text_color=TEXT,
            justify="left",
        ).pack(anchor="w", padx=24, pady=(4, 14))
        if error is not None:
            ctk.CTkLabel(
                card,
                text=f"验收失败：{error}",
                font=self._font(12),
                text_color=DANGER,
                wraplength=800,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(0, 10))
        if progress:
            ctk.CTkLabel(
                card,
                text="正在验收…",
                font=self._font(14, True),
                text_color=WARN,
            ).pack(anchor="w", padx=24, pady=10)
            return
        button = ctk.CTkButton(
            card,
            text="我已冷启动，继续",
            width=180,
            height=42,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=self._font(13, True),
            command=self._verify_after_boot,
        )
        button.pack(anchor="w", padx=24, pady=(0, 18))
        self.action_buttons = [button]

    def _verify_after_boot(self) -> None:
        if self.upstream is None or self._busy:
            return
        self._log("用户操作：冷启动后开始验收")
        self._show_step(4, progress=True)
        self._run_task(
            "验收",
            lambda: verify_step.run(
                self.upstream,
                self.runs_dir,
                runtime_check=True,
            ),
            self._verify_done,
        )

    def _verify_done(self, result, error) -> None:
        if error is not None:
            self._show_step(5, error=str(error))
            return
        expected_id = (self.install_facts or {}).get("body_id")
        actual_id = result.get("body_id")
        if expected_id and actual_id and expected_id != actual_id:
            self._show_step(
                5,
                error=f"相机身份与安装时不一致：{expected_id} vs {actual_id}",
            )
            return
        self.verify_result = result
        self._show_step(5, result=result)

    # -- step 5: acceptance / WBI -----------------------------------------
    def _build_step_5(
        self,
        result=None,
        error=None,
        progress=False,
        wbi_state=None,
        wbi_prep=None,
    ) -> None:
        card = self._card(self.content)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(
            card, text="第 5 步 · 验收", font=self._font(20, True), text_color=TEXT
        ).pack(anchor="w", padx=24, pady=(18, 2))
        if progress:
            ctk.CTkLabel(
                card,
                text="正在进行 WBI 检查/写入…",
                font=self._font(14, True),
                text_color=WARN,
            ).pack(anchor="w", padx=24, pady=18)
            return
        if error is not None:
            ctk.CTkLabel(
                card,
                text=f"❌ {error}",
                font=self._font(13, True),
                text_color=DANGER,
                wraplength=800,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(8, 12))
            button = ctk.CTkButton(
                card,
                text="重新验收",
                width=130,
                height=38,
                corner_radius=10,
                fg_color=SECONDARY,
                hover_color=SECONDARY_HOVER,
                text_color=TEXT,
                font=self._font(12, True),
                command=self._verify_after_boot,
            )
            button.pack(anchor="w", padx=24, pady=(0, 18))
            self.action_buttons = [button]
            return

        status = (result or {}).get("status")
        if status == "ok":
            ctk.CTkLabel(
                card,
                text="✅ 完成：5GHz 菜单已生效",
                font=self._font(18, True),
                text_color=OK,
            ).pack(anchor="w", padx=24, pady=(12, 6))
            ctk.CTkLabel(
                card,
                text=(
                    "请在相机上打开 Network → Wi-Fi Settings → Frequency Band，"
                    "应能看到 2.4GHz / 5GHz 选项。"
                ),
                font=self._font(12),
                text_color=TEXT,
                wraplength=800,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(0, 6))
            runtime = (result or {}).get("runtime") or {}
            if runtime:
                ctk.CTkLabel(
                    card,
                    text=f"运行期检查：加载字节 {runtime.get('byte')} @ {runtime.get('address')}",
                    font=self._font(11),
                    text_color=OK,
                ).pack(anchor="w", padx=24, pady=(0, 4))
            if result.get("body_id"):
                ctk.CTkLabel(
                    card,
                    text=f"机身 ID：{result.get('body_id')}",
                    font=self._font(11),
                    text_color=MUTED,
                ).pack(anchor="w", padx=24, pady=(0, 10))
            button = ctk.CTkButton(
                card,
                text="完成",
                width=120,
                height=38,
                corner_radius=10,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                font=self._font(12, True),
                command=self._on_close,
            )
            button.pack(anchor="w", padx=24, pady=(0, 18))
            self.action_buttons = [button]
            return

        if status == "wbi_required" and not self.wbi_attempted:
            ctk.CTkLabel(
                card,
                text="补丁已写入，但菜单还未生效。需要 WBI 清除旧缓存。",
                font=self._font(14, True),
                text_color=WARN,
                wraplength=800,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(8, 6))
            ctk.CTkLabel(
                card,
                text=(
                    "WBI 会清除相机暖启动缓存。它写入 eMMC，没有硬件验证过的回滚；"
                    "请确认你具备恢复路线。"
                ),
                font=self._font(11),
                text_color=MUTED,
                wraplength=800,
                justify="left",
            ).pack(anchor="w", padx=24, pady=(0, 8))
            tool_text = (
                f"已选择：{self.wbi_tool.name}" if self.wbi_tool else "尚未选择 Sony 官方工具"
            )
            ctk.CTkLabel(
                card, text=tool_text, font=self._font(12), text_color=TEXT
            ).pack(anchor="w", padx=24)
            tool_button = ctk.CTkButton(
                card,
                text="选择 Sony 官方 ud_wbi_drop.elf",
                width=230,
                height=34,
                corner_radius=10,
                fg_color=SECONDARY,
                hover_color=SECONDARY_HOVER,
                text_color=TEXT,
                font=self._font(12),
                command=self._choose_wbi_tool,
            )
            tool_button.pack(anchor="w", padx=24, pady=(6, 10))

            self.recovery_var = tk.BooleanVar(value=self.recovery_confirmed)
            ctk.CTkCheckBox(
                card,
                text="我已具备 Pico/BootROM + fastboot 恢复路线（本工具无法验证硬件）",
                variable=self.recovery_var,
                font=self._font(12),
                checkbox_width=20,
                checkbox_height=20,
                command=self._on_recovery_change,
            ).pack(anchor="w", padx=24, pady=4)

            if wbi_state == "prepared":
                ctk.CTkLabel(
                    card,
                    text="✅ WBI 条件检查通过：两次备份一致，等待确认。",
                    font=self._font(12, True),
                    text_color=OK,
                ).pack(anchor="w", padx=24, pady=(8, 4))
                execute_button = ctk.CTkButton(
                    card,
                    text="执行 WBI 失效",
                    width=170,
                    height=40,
                    corner_radius=10,
                    fg_color=DANGER,
                    hover_color="#B91C1C",
                    font=self._font(13, True),
                    command=self._execute_wbi,
                )
                execute_button.pack(anchor="w", padx=24, pady=(0, 8))
                cancel_button = ctk.CTkButton(
                    card,
                    text="取消并关闭 WBI 会话",
                    width=170,
                    height=34,
                    corner_radius=10,
                    fg_color=SECONDARY,
                    hover_color=SECONDARY_HOVER,
                    text_color=TEXT,
                    font=self._font(12),
                    command=self._cancel_wbi,
                )
                cancel_button.pack(anchor="w", padx=24, pady=(0, 12))
                self.action_buttons = [execute_button, cancel_button]
                return

            check_button = ctk.CTkButton(
                card,
                text="检查 WBI 条件（两次 60 MiB 备份）",
                width=260,
                height=38,
                corner_radius=10,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                font=self._font(12, True),
                command=self._check_wbi,
                state="normal" if (self.wbi_tool and self.recovery_confirmed) else "disabled",
            )
            check_button.pack(anchor="w", padx=24, pady=(8, 18))
            self.action_buttons = [check_button, tool_button]
            return

        if status == "wbi_required" and self.wbi_attempted:
            text = "WBI 已执行，但菜单仍未生效。请停止并保留证据，不要重复写入。"
        elif (result or {}).get("runtime_error"):
            text = f"运行期检查失败：{(result or {}).get('runtime_error')}"
        else:
            text = "验收未通过。请冷启动后重试；如果仍然失败，请保留证据。"
        ctk.CTkLabel(
            card,
            text=f"❌ {text}",
            font=self._font(13, True),
            text_color=DANGER,
            wraplength=800,
            justify="left",
        ).pack(anchor="w", padx=24, pady=(8, 12))
        button = ctk.CTkButton(
            card,
            text="重新验收",
            width=130,
            height=38,
            corner_radius=10,
            fg_color=SECONDARY,
            hover_color=SECONDARY_HOVER,
            text_color=TEXT,
            font=self._font(12, True),
            command=self._verify_after_boot,
        )
        button.pack(anchor="w", padx=24, pady=(0, 18))
        self.action_buttons = [button]

    def _on_recovery_change(self) -> None:
        self.recovery_confirmed = bool(self.recovery_var.get())
        if self.step == 5 and self.verify_result is not None:
            self._show_step(5, result=self.verify_result)

    def _choose_wbi_tool(self) -> None:
        path = filedialog.askopenfilename(
            title="选择你从官方 2.03 更新包提取的 ud_wbi_drop.elf",
            filetypes=[("ELF files", "*.elf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.wbi_tool = wbi_step.validate_tool(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("工具校验失败", str(exc))
            return
        self._show_step(5, result=self.verify_result)

    def _check_wbi(self) -> None:
        if self._busy or self.wbi_tool is None or not self.recovery_confirmed:
            return
        self._show_step(5, result=self.verify_result, progress=True)

        def prepare():
            session = wbi_step.WbiSession(self.upstream, self.runs_dir)
            try:
                prep = session.prepare(self.wbi_tool)
            except Exception:
                session.close()
                raise
            return {"session": session, "prep": prep}

        self._run_task("WBI 检查", prepare, self._wbi_check_done)

    def _wbi_check_done(self, result, error) -> None:
        if error is not None:
            text = str(error)
            if "already invalid" in text.lower() or "already-invalid" in text.lower():
                self._show_step(
                    5,
                    result=self.verify_result,
                    error="WBI 已失效，可能是菜单已重建；请重新冷启动并验收。",
                )
            else:
                self._show_step(5, result=self.verify_result, error=text)
            return
        self.wbi = result["session"]
        self.wbi_prepared = result["prep"]
        self._show_step(5, result=self.verify_result, wbi_state="prepared", wbi_prep=result["prep"])

    def _execute_wbi(self) -> None:
        if self._busy or self.wbi is None or self.wbi_prepared is None:
            return
        confirmation = str(self.wbi_prepared.get("confirmation", ""))
        answer = ctk.CTkInputDialog(
            text=f"逐字输入确认字符串以执行 WBI 失效：\n{confirmation}",
            title="WBI 写入确认",
        ).get_input()
        if answer is None or answer.strip() != confirmation:
            self._log("WBI 确认不匹配，未写入。")
            return
        self.wbi_attempted = True
        self._show_step(5, result=self.verify_result, progress=True)
        self._run_task(
            "WBI 失效",
            lambda: self.wbi.execute(confirmation, recovery_ready=True),
            self._wbi_done,
        )

    def _wbi_done(self, result, error) -> None:
        if error is not None:
            self._show_step(5, result=self.verify_result, error=f"WBI 写入失败：{error}")
            self.wbi = None
            self.wbi_prepared = None
            return
        self.wbi = None
        self.wbi_prepared = None
        self._show_step(4, wbi_done=True)

    def _cancel_wbi(self) -> None:
        if self.wbi is not None:
            try:
                self.wbi.close()
            except Exception:
                pass
            self.wbi = None
            self.wbi_prepared = None
        self._show_step(5, result=self.verify_result)

    # -- task runner / log -------------------------------------------------
    def _run_task(self, name: str, action, on_done) -> None:
        if self._busy:
            return
        self._busy = True
        for button in getattr(self, "action_buttons", []):
            try:
                button.configure(state="disabled")
            except Exception:
                pass
        self._log(f"{name} 开始…")

        def worker() -> None:
            try:
                result = action()
                error = None
            except Exception as exc:  # noqa: BLE001
                result, error = None, exc
            self.after(0, lambda: self._task_done(name, result, error, on_done))

        threading.Thread(target=worker, daemon=True).start()

    def _task_done(self, name: str, result, error, on_done) -> None:
        self._busy = False
        if error is not None:
            detail = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            self._log(f"{name} 失败：{error}\n{detail}")
        else:
            self._log(f"{name} 完成")
        on_done(result, error)

    def _log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        self.log_lines.append(line)
        if self.log_path is not None:
            try:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                pass
        if self.tech_window is not None and self.tech_window.winfo_exists():
            self.tech_window.append(line)

    def _open_tech(self) -> None:
        if self.tech_window is not None and self.tech_window.winfo_exists():
            self.tech_window.lift()
            return
        self.tech_window = TechWindow(self, self)

    # -- errors ------------------------------------------------------------
    def _friendly_error(self, error: Exception) -> str:
        text = str(error)
        lowered = text.lower()
        if "already installed" in lowered or "baseline_properties" in lowered:
            return "这台相机已经刷过（属性 01/02/16），不需要重复刷入。"
        if "camera 054c" in lowered or "no authenticated camera" in lowered:
            return "没有找到相机。请确认 USB 线、Mass Storage 模式和驱动。"
        if "wbi is already invalid" in lowered:
            return "WBI 已失效，无需重复执行。"
        return text

    # -- close -------------------------------------------------------------
    def _on_close(self) -> None:
        if self._busy:
            messagebox.showinfo("请稍候", "操作进行中，请等待完成后再关闭。")
            return
        if self.install is not None:
            try:
                self.install.close()
            except Exception:
                pass
        if self.wbi is not None:
            try:
                self.wbi.close()
            except Exception:
                pass
        self.destroy()


class TechWindow(ctk.CTkToplevel):
    """Technical tools and logs, hidden from the main flow."""

    def __init__(self, app: InstallerApp, master) -> None:
        super().__init__(master)
        self.app = app
        self.title("技术详情 / 高级")
        self.geometry("760x560")
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(
            self, text="技术详情", font=app._font(18, True), text_color=TEXT
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="只读诊断工具；不影响主流程。",
            font=app._font(11),
            text_color=MUTED,
        ).pack(anchor="w", padx=20)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(10, 4))
        for title, command in (
            ("环境检查", self._doctor),
            ("读取状态", self._inspect),
            ("验收检查", self._verify),
            ("导出诊断包", self._diagnostics),
        ):
            ctk.CTkButton(
                row,
                text=title,
                width=110,
                height=32,
                corner_radius=9,
                fg_color=SECONDARY,
                hover_color=SECONDARY_HOVER,
                text_color=TEXT,
                font=app._font(11, True),
                command=command,
            ).pack(side="left", padx=(0, 8))

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(0, 8))
        for title, command in (
            ("上次运行", self._history),
            ("自检", self._selfcheck),
        ):
            ctk.CTkButton(
                row2,
                text=title,
                width=110,
                height=32,
                corner_radius=9,
                fg_color=SECONDARY,
                hover_color=SECONDARY_HOVER,
                text_color=TEXT,
                font=app._font(11, True),
                command=command,
            ).pack(side="left", padx=(0, 8))

        self.textbox = ctk.CTkTextbox(
            self,
            corner_radius=12,
            fg_color=OUTPUT_BG,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            font=ctk.CTkFont(family=MONO, size=11),
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.textbox.configure(state="disabled")
        for line in app.log_lines:
            self.append(line)

    def append(self, line: str) -> None:
        self.textbox.configure(state="normal")
        self.textbox.insert("end", line + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def _busy(self) -> bool:
        if self.app.install is not None or self.app.wbi is not None:
            messagebox.showinfo("会话占用", "当前有刷入或 WBI 会话，请先完成或取消。")
            return True
        return False

    def _doctor(self) -> None:
        if self.app.upstream is None:
            return
        checks = doctor.run(self.app.upstream)
        self.append(doctor.format_checks(checks))

    def _inspect(self) -> None:
        if self._busy() or self.app.upstream is None:
            return

        def worker() -> None:
            try:
                summary = inspect_step.run(self.app.upstream, self.app.runs_dir)
                self.app.after(0, lambda: self.append(str(summary)))
            except Exception as exc:  # noqa: BLE001
                self.app.after(0, lambda: self.append(f"读取失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _verify(self) -> None:
        if self._busy() or self.app.upstream is None:
            return

        def worker() -> None:
            try:
                summary = verify_step.run(self.app.upstream, self.app.runs_dir)
                self.app.after(0, lambda: self.append(str(summary)))
            except Exception as exc:  # noqa: BLE001
                self.app.after(0, lambda: self.append(f"验收失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _diagnostics(self) -> None:
        if self.app.upstream is None:
            return

        def worker() -> None:
            try:
                path = diagnostics.create_bundle(
                    self.app.runs_dir,
                    self.app.upstream,
                    extra={
                        "gui_log": str(self.app.log_path) if self.app.log_path else "",
                        "gui_version": __version__,
                    },
                )
                self.app.after(
                    0,
                    lambda: self.append(
                        f"诊断包：{path}\n（包含本机路径与日志，公开分享前请检查）"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                self.app.after(0, lambda: self.append(f"导出诊断包失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _history(self) -> None:
        last = history.latest(self.app.runs_dir)
        if last is None:
            self.append("没有上次运行记录。")
            return
        lines = [
            f"上次运行：{last['label']}",
            f"阶段: {last['stage']}",
            f"目录: {last['run_dir']}",
            f"时间: {last.get('updated')}",
        ]
        if last.get("error"):
            lines.append(f"错误: {last['error']}")
        self.append("\n".join(lines))

    def _selfcheck(self) -> None:
        if self.app.upstream is None:
            return
        checks = selfcheck.run(self.app.upstream)
        self.append(selfcheck.format_checks(checks))


def main() -> int:
    app = InstallerApp()
    if "--smoke-test" in sys.argv:
        app.after(1800, app.destroy)
    app.mainloop()
    return 0
