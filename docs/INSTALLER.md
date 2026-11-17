# ZV-E10 Guided Installer

受控引导式安装器，用于索尼 ZV-E10（一代，2.02 / 2.03）恢复原生 5GHz 频段菜单。

> **这不是一键刷机工具。**
> 每一步写入都要求人工确认；WBI 默认关闭；不内置 Sony 二进制；不自动重试；不承诺恢复。
>
> 仅在中国大陆 B=2 / C=22 有功能证据。改机可能影响保修，5GHz 使用受当地法规约束。
> 本项目与索尼无关，未获官方支持。

## 当前版本（v0.12）

v0.12 的 GUI 是五步向导：准备 → 检查 → 刷入 → 冷启动 → 验收；验收未生效时自动进入 WBI 步骤。前提条件、驱动助手、技术工具的位置见下面的“独立 exe”一节。CLI 保留 `doctor` / `inspect` / `install` / `verify` / `wbi`，并新增实验性的 `sound-inspect` / `sound-write` / `sound-write-all` / `sound-restore-all`。

## 前置条件

- 上游主仓库：`dino2048/ZV-E10-5GHz-WiFi-Unlock`
- 工具包：`dino2048/zv-e10-toolkit`，固定提交 `373bd48`
- Sony-PMCA-RE：固定修订 `a82f5ba`
- Python 3.10+
- 相机 USB 为 Mass Storage；Windows 上需绑定 WinUSB

安装器不自动克隆上游，也不修改上游文件。`--upstream` 指向一个符合固定提交的本地 checkout。

## 快速开始（Windows）

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe inspect --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe install --upstream "D:\path\to\unlock"
# cold boot the camera, then:
.\.venv\Scripts\zve10-installer.exe verify --upstream "D:\path\to\unlock"
```

`install` 的整盘备份使用 `raw-backup`（默认单趟、4 MiB 块），在 2.03 上约 15 分钟；
会话空闲超时是 1 小时，活跃备份不消耗空闲预算。

`verify` 的退出码：`0` = `TypeNB/5`；`4` = 补丁与属性正确但 `Page1` 仍是 `TypeRK/4`（需要 WBI，v0.2 不执行）；`3` = 错误。

`inspect` 结果写入 `runs/<timestamp>-inspect-<id>/summary.json`，上游会话快照保留在同一目录的 `session/` 下。

## 独立 exe（v0.12）

构建后得到两个单文件程序：

| 文件 | 类型 |
|---|---|
| `dist\ZV-E10-Installer.exe` | **GUI**，浅色五步向导，推荐给普通用户 |
| `dist\zve10-installer.exe` | 控制台 CLI，适合脚本和调试 |

### 五步向导

```text
① 准备 → ② 检查 → ③ 刷入 → ④ 冷启动 → ⑤ 验收
                                      └─ 菜单未生效 → 自动进入 WBI 步骤
```

**① 准备（前提条件卡）**

| 条件 | 说明 |
|---|---|
| 相机 | ZV-E10 一代 |
| 固件 | 2.02 / 2.03（检查时自动读取） |
| USB 模式 | **Mass Storage / 海量存储器** |
| 数据线 | 支持数据传输的 USB-C 线 |
| 驱动 | WinUSB 已绑定；未绑定时点“安装驱动” |
| 区域 | 中国大陆 B=2 / C=22（勾选确认） |
| 电量 | 输入相机显示的电量，至少 50% |
| 第二份备份 | 必须选择一个**空目录**，建议放在另一块磁盘 |
| 备份 | 程序自动做整盘备份，并复制到第二份目录逐字节校验 |

**② 检查**：先做约 2 分钟的**只读连接稳定性测试**（重复读取，哈希和属性必须一致），
然后做整盘备份（约 15 分钟），并把所有备份文件复制到第二份目录逐字节比对。
任何一项不满足，界面会说明原因，不允许继续。

**③ 刷入**：写入单字节补丁 + 三个属性；需要逐字输入 `PATCH ZV-E10 2.03`。
写入后会读取完整 Backup 数据库，确认三个目标属性之外没有变化；准备期间已变化的
运行时计数器会被记录并允许，其余任何变化都会停止验收并要求复核。

**④ 冷启动**：界面给出关机、拔线、取电池 30 秒、开机、Mass Storage 的步骤。

**⑤ 验收**：自动运行只读 `verify`，并读取运行中的 `CautionConfig.so` 目标字节（`0x1B`）。
- 菜单生效：完成。
- 仍是旧菜单：**同一页面自动进入 WBI 步骤**，不需要用户自己找入口。

> 运行期字节检查需要一个带诊断写标志的会话，但程序只发送读取命令，不写相机。
> 每次验收都会记录机身 ID 哈希（来自 Backup 序列号属性，不保存原始序列号）。

### 驱动助手（离线内置）

- 内置 **Zadig 2.9**（GPLv3，独立程序，不链接进安装器），不需要在线下载。
- 点击“安装驱动”会打开 Zadig；选择 `ZV-E10`、`WinUSB`、`Install Driver`，完成后回到程序点“重新检测”。
- 如果软件或 Zadig 里还出现第二个 Sony USB 身份（例如 `Sony USB Device`），也要给它装 WinUSB；`doctor` 会列出当前所有 `054c` 产品 ID。
- “驱动恢复”会打开设备管理器，按提示卸载相机驱动并恢复 Windows 默认连接。
- 需要管理员权限；工具不会静默安装驱动。
- 许可证与源码地址见 `vendor/zadig/COPYING.txt` 和 `vendor/zadig/SOURCE.txt`。

### 自动 WBI 步骤

验收发现菜单未生效时，同一页面会显示 WBI 步骤：

- 选择你从官方 2.03 更新包提取的 `ud_wbi_drop.elf`（6,200 字节，哈希必须匹配）；
- 勾选确认已具备 Pico/BootROM + fastboot 恢复路线（工具无法验证硬件）；
- 检查会做两次完整 60 MiB 读取和逐字节比对；
- 只有逐字输入返回的 `INVALIDATE WBI <hash>` 确认字符串才会执行 drop；
- 已失效的 WBI 会返回 `already-invalid`，直接拒绝重复写入。

### 技术工具

`Doctor / Inspect / Verify`、**导出诊断包**、**上次运行**、**自检**和日志移到“技术详情 / 高级”按钮里，主流程只显示用户需要看的内容。
诊断包只包含环境、doctor 结果和最近几次运行的日志/状态，不包含备份、固件、helper 或 Sony 工具。

离线自检（不连接相机）：

```powershell
.\dist\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
```

它会核对上游固定提交、`patch.arm`/`restore.arm` 哈希、`tools/wifi.py`/`wbi.py`、
Windows 垫片和内置 Zadig 的哈希。

> **重要**：`install` 和 WBI 的写入路径已实现并有门禁，但尚未在工厂状态相机上完成端到端验证。
> 当前这台相机已是 `01/02/16` 且 WBI 已失效，条件检查会明确拒绝。

## 快门声音（实验）

参考 `cokeenet/zve10-qemu` 的公开研究：ZV-E10 的快门音效在
`/usr/share/avsystemsound/*.bin`，格式是 24 kHz、32 字节一块的自研 ADPCM，
不是 WAV/MP3。参考仓库是 **PolyForm Noncommercial** 许可，本项目只采用其格式事实，
编解码为独立实现。

离线转换（不连接相机）：

```powershell
.\dist\zve10-installer.exe sound-decode "Dslr_Emnt_Shutter_Sha.bin" --out "orig.wav"
.\dist\zve10-installer.exe sound-convert "my.wav" --out "my.bin" --preview "my.preview.wav"
```

音频要求：

- PCM WAV（未压缩整数），建议 16-bit、48 kHz、单声道；
- 最长 1.0 秒；建议 0.1–0.5 秒；
- 峰值约 -6 dBFS，不要削波；
- 输出 32 字节块，最大 24,832 字节。

### 相机写入（v0.11，实验）

先只读读取相机上的原厂快门音效并保存到 `runs/<...>/original/`：

```powershell
.\dist\zve10-installer.exe sound-inspect --upstream "D:\path\to\unlock"
```

对照测试：只替换 `Dslr_Emnt_Shutter_Sha.bin`。用 `sound-decode` 解码相机原厂文件得到 WAV，再用 `sound-convert` 编码回 BIN；该 BIN 的音频内容与原厂相同，哈希不同。先 `sound-inspect` 取得相机当前文件的完整 sha256，再写入：

```powershell
.\dist\zve10-installer.exe sound-write --upstream "D:\path\to\unlock" `
  --name Dslr_Emnt_Shutter_Sha.bin --file "control.bin" `
  --expected "<sound-inspect 显示的 sha256>" `
  --confirm "WRITE Dslr_Emnt_Shutter_Sha.bin"
```

写入路径的门禁与步骤：

1. 会话以 `--owner-authorized-write` 启动，但只接受 `sound-read` / `sound-write`；
2. 写入前重新读取目标文件，sha256 必须等于 `--expected`，否则拒绝；
3. 把当前文件保存到会话目录（`*.before`），并在主机侧另存一份；
4. 通过上游 Jiritsu SET_FILE2 上传替换文件并完整回读；
5. 确认 `/usr` 是 `/dev/nflasha15 ext2 ro` 后 remount rw，并再次确认已是 rw；
6. 先把替换文件写进同目录的隐藏临时名，`chmod 644`、`sync`、**回读临时文件逐字节一致**；
7. 用 `busybox mv` 在同一目录原子替换目标文件，再回读目标文件逐字节一致；
8. **无论成功失败都在 `finally` 中清理临时文件、remount ro 并复核**；失败会明确报错，不自动重试；
9. 完成后必须**冷启动**相机再试听；不需要 WBI。

如果对照测试成功，或者想直接覆盖所有可能的 beep type（公开研究建议的“路 2”），
用同一个 BIN 一次写入全部 9 个 `Shutter*` / `10FPS_Kasha*` / `Shutter_Ka` 文件：

```powershell
.\dist\zve10-installer.exe sound-write-all --upstream "D:\path\to\unlock" `
  --file "my.bin" --confirm "WRITE ALL SHUTTER"
```

每个文件写入前都会重新读取并把当前内容保存到 `original/`，用当前 sha256 作为该文件的
`--expected`。任何一个文件失败会立即停止，报告已经改了哪些，不自动重试。

> 为什么可能需要全部 9 个：相机不是固定读取某一个文件，而是从 Backup 的 beep type
> 决定播放哪一套。只换 `Sha` 只对 beep type=2 生效；全部替换则不依赖这个值。
> 如果全部替换后仍然听不到自定义声音，说明快门声不是从 `avsystemsound` 播放的，
> 不应继续改 DSP/`av-cam.bin`。（2026-11-17 已实测：9 个全部替换后仍无变化。）

### 一键回退原厂声音（v0.12）

`sound-inspect` 已经把 9 个原厂文件保存到 `runs/<时间>-sound-<id>\original\`。需要回退时：

```powershell
.\dist\zve10-installer.exe sound-restore-all `
  --from "runs\<sound-run>" `
  --confirm "RESTORE ALL SHUTTER"
```

- `--from` 可以是 sound 运行目录，也可以直接指向其中的 `original\`。
- 打开相机会话前会预检 9 个文件都存在，且 sha256 等于官方 2.03 镜像；任何一个缺失或不对，整次回退拒绝，不会写相机。
- 已经是原厂状态的文件会跳过，只写回被改过的文件。
- 回退后冷启动，再跑 `sound-inspect`，哈希应恢复为 `957ae893…` / `e932f708…` / `0ef38673…` / `3cff4023…`。
- 预检只接受官方 2.03 的哈希；2.02 或不同区域的备份请逐个用 `sound-write` 写回。

GUI 目前还没有声音面板，声音功能只在 CLI。

### 真机结果（2026-11-17，ZV-E10 2.03）

- 自定义音频（24,320 字节）写入全部 9 个槽位，逐文件回读和冷启动持久化均通过；
- 冷启动后 `sound-inspect` 显示 9/9 仍是自定义哈希，但快门声没有变化；
- 用 `sound-restore-all` 写回 9 个原厂文件，再冷启动，9/9 全部 `matches_image: true`。
- 结论：这台 2.03 不把 `/usr/share/avsystemsound/*.bin` 作为快门声源（beep type/DSP 侧），
  不要继续改 DSP/`av-cam.bin`。写入、持久化和一键回退工具本身已经验证。

> `install` 的工厂状态端到端验证仍未完成；声音写入/回退是另一条独立路径。

## 验证状态

| 范围 | 状态 |
|---|---|
| 手工流程：补丁 + 三个属性 + WBI | 在作者的一台 ZV-E10 2.03 上完成实机写入、回读和冷启动验收 |
| 安装器只读 `verify` | 在同一台相机上实机通过（`TypeNB/5`、`01/02/16`、`/usr ro`） |
| 安装器 `install` 写入 | 代码、门禁和离线测试完成；**未在工厂状态相机上端到端验证** |
| WBI 高级模式 | `already-invalid` 拒绝路径已实测；有效 WBI 的 drop 未重测 |
| 驱动安装 | 未在“驱动未绑定”的机器上实测；内置 Zadig 2.9 签名/哈希已校验 |
| 稳定性测试 / 双备份 / 诊断包 / 临时文件守卫 | 离线测试通过；真实硬件路径待工厂相机验证 |
| 运行期字节检查 / 机身 ID | 代码和映射解析已离线测试；真实运行期读取待相机验证 |
| 快门声音写入 / 回退 | 在 ZV-E10 2.03 上写入 9 个槽位、冷启动持久化、恢复 9/9 原厂均通过；相机未播放自定义音色 |
| macOS / Linux | 未验证 |
| 5GHz 实际传输/测速 | 未做受控测试；菜单出现不等于射频已验收 |

目前只在一台相机上验证过；各版本的检查记录见 [CHANGELOG.md](../CHANGELOG.md)。

```powershell
.\dist\ZV-E10-Installer.exe
```

只读构建（隐藏 `install` / `wbi`）：

```powershell
$env:ZVE10_READ_ONLY_BUILD="1"
.\scripts\build_exe.ps1 -Upstream "D:\path\to\unlock"
```

特点：

- 内置固定提交的上游代码、Windows 垫片、`pyusb`/libusb DLL、CustomTkinter、Zadig 2.9。
- `PIN.json` 记录并校验上游提交；完整构建不包含 `READ_ONLY` 标记。
- 不包含 Sony 的 `ud_wbi_drop.elf`、固件、BootROM dump 或设备备份。
- 单文件运行时解压到 `%TEMP%\_MEI...`，首次启动需要几秒；未签名，可能出现 SmartScreen/杀软提示。

## 安全设计

- 只调用上游 `tools/wifi.py` 与 toolkit 的 server/client，不重写 USB/队列/认证/Backup 协议。
- 不提供 `--force`；写入相关确认必须逐字输入。
- 写入后超时、短读、哈希不符 → 标记 `UNKNOWN`，禁止开新会话，先只读复核。
- WBI 是独立高级命令，默认拒绝；需要恢复路线和逐字确认。
- `runs/`、`private/`、设备备份均被 `.gitignore` 忽略。

## 许可

MIT。上游项目的版权与许可见 [NOTICE.md](../NOTICE.md)。Sony 的 `ud_wbi_drop.elf`、固件、BootROM dump 不随本项目分发。
