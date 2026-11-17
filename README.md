# ZV-E10 固件研究：服务模式、5 GHz 解锁与快门声音实验

本仓库记录 Sony ZV-E10（ILCE-ZV-E10，系统版本 `30110_06.2026060501`，即 2.03）在 Windows 主机上的服务模式访问、5 GHz 菜单恢复、受控安装器实现，以及快门声音文件替换实验。记录时间为 2026-11-16 至 2026-11-17。

仓库内容为源码、测试、门禁设计、操作记录和失败复盘。仓库不包含 Sony 固件、`ud_wbi_drop.elf`、设备备份、`private/` 会话数据、序列号、MAC 地址、密钥或第三方二进制。

## 结果摘要

| 方向 | 结果 |
|---|---|
| 5 GHz 菜单 | 在单台 ZV-E10 2.03 上完成 `CautionConfig.so` 单字节补丁、三个 Backup 属性和 WBI 失效。冷启动后 `Page1=TypeNB/5`，相机菜单出现 5 GHz 频段选项。射频链路未做受控测试。 |
| 受控安装器 | 源码、状态机、门禁、双备份、保留性检查、运行期字节检查和五步 GUI 已完成。只读 `verify` 在实机通过；`install` 写入尚未在工厂状态相机上完成端到端验证。 |
| 快门声音 | 9 个 `avsystemsound` 槽位的写入、逐文件回读、冷启动持久化和一键恢复在实机通过。相机未播放自定义音色。该固件的快门声不来自这些文件。 |
| 离线测试 | 43 项 pytest 通过。覆盖门禁、状态机、备份、稳定性、保存性、声音编解码、声音服务读写和恢复预检。 |

## 适用范围

- 相机：Sony ZV-E10 一代，固件 2.02 / 2.03；实际写入验证在 2.03 上完成。
- 区域：仅中国大陆 `B=2 / C=22` 有功能证据。
- 主机：Windows 10/11 x64；USB Mass Storage；WinUSB 绑定。
- 上游：`dino2048/ZV-E10-5GHz-WiFi-Unlock`、`dino2048/zv-e10-toolkit`、`Sony-PMCA-RE`，固定提交见 [NOTICE.md](NOTICE.md)。

## 仓库结构

```text
src/zve10_installer/       安装器、CLI、GUI、状态机、门禁、声音编解码与服务端
tests/                     离线测试
packaging/                 PyInstaller 配置与冻结入口
scripts/                   环境引导与构建脚本
compat/windows/            Windows 的 uid/chown/pwd 与 libusb 兼容垫片
docs/INSTALLER.md          安装器使用说明
docs/TESTER-GUIDE.md       测试者操作与日志回传要求
docs/RESEARCH.md           5 GHz、安装器和快门声音的完整研究记录
CHANGELOG.md               版本与真机结果
```

## 构建

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
```

`--upstream` 指向符合固定提交的本地 checkout。安装器不自动克隆上游，也不修改上游文件。构建单文件程序：

```powershell
.\scripts\build_exe.ps1 -Upstream "D:\path\to\unlock"
```

构建脚本默认使用 `.venv\Scripts\pyinstaller.exe`；可通过 `ZVE10_PYINSTALLER` 指向其他 PyInstaller。Zadig 2.9 为 GPLv3 独立程序，仓库不包含其二进制；需要驱动助手时按 [vendor/zadig/SOURCE.txt](vendor/zadig/SOURCE.txt) 获取。

## 安全边界

- 不自动执行 WBI。WBI 是对 `/dev/nflasha5` 前 512 字节的 eMMC 写入，本次操作在无 Pico/BootROM 恢复路线的条件下由机主明确授权执行，属于偏离上游恢复路线要求的操作。不要重复执行。
- 写入前必须完成整盘备份、第二份逐字节备份、连接稳定性测试和保留性检查。
- 写入失败、超时或回读不一致时，状态标记为 `UNKNOWN`，禁止开新会话重试；先做只读复核。
- 不包含 Sony 的 `ud_wbi_drop.elf`、固件、BootROM dump、设备备份或密钥。
- `runs/` 与上游会话目录可能包含设备标识和完整库快照，保持私有，不要提交或公开。
- 修改相机固件可能影响保修；5 GHz 使用受当地法规约束。

## 文档

- [研究记录](docs/RESEARCH.md)：5 GHz 解锁、安装器门禁、快门声音实验、失败与修正。
- [安装器说明](docs/INSTALLER.md)：GUI 流程、CLI 命令、驱动、备份与验收。
- [测试者说明](docs/TESTER-GUIDE.md)：只读测试、诊断包和禁止回传的数据。
- [变更记录](CHANGELOG.md)：版本历史和 2026-11-17 真机结果。

## 许可

本仓库代码采用 MIT 许可。上游项目、Sony-PMCA-RE 和 Zadig 的许可与固定提交见 [NOTICE.md](NOTICE.md)。`cokeenet/zve10-qemu` 采用 PolyForm Noncommercial 1.0.0；本仓库仅引用其公开的格式事实，未复制其代码。
