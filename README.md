# ZV-E10 Firmware Research and Gate-Enforced Installer Framework

Research records and a controlled Windows installer framework for the Sony ZV-E10 (ILCE-ZV-E10), firmware 2.02/2.03. Current modules cover 5 GHz menu restoration and an evaluated shutter-sound replacement attempt. Every write step remains behind explicit gates, backups, and rollback checks.

本仓库记录 Sony ZV-E10（ILCE-ZV-E10，固件 2.02/2.03）的服务模式访问、5 GHz 菜单恢复、受控安装器实现和快门声音文件替换实验。当前所有写入仍受门禁、备份和回滚检查约束。

## 中文

### 范围与结论

| 方向 | 结果 |
|---|---|
| 5 GHz 菜单 | 在单台 ZV-E10 2.03 上完成 `CautionConfig.so` 单字节补丁、三个 Backup 属性和 WBI 失效。冷启动后 `Page1=TypeNB/5`，菜单出现 5 GHz 频段选项。射频链路未做受控测试。 |
| 受控安装器 | 源码、状态机、门禁、双备份、保留性检查、运行期字节检查和五步 GUI 已完成。只读 `verify` 在实机通过；`install` 写入尚未在工厂状态相机上完成端到端验证。 |
| 快门声音 | 9 个 `avsystemsound` 槽位的写入、逐文件回读、冷启动持久化和一键恢复在实机通过。相机未播放自定义音色；该固件的快门声不来自这些文件。 |
| 离线测试 | 43 项 pytest 通过。覆盖门禁、状态机、备份、稳定性、保留性、声音编解码、声音服务读写和恢复预检。 |

### 仓库结构

```text
src/zve10_installer/       安装器、CLI、GUI、状态机、门禁、声音编解码与服务端
tests/                     离线测试
packaging/                 PyInstaller 配置与冻结入口
scripts/                   环境引导与构建脚本
compat/windows/            Windows 的 uid/chown/pwd 与 libusb 兼容垫片
docs/INSTALLER.md          安装器使用说明
docs/TESTER-GUIDE.md       测试者操作与日志回传要求
docs/RESEARCH.md           5 GHz、安装器和快门声音的完整研究记录
```

### 构建

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
```

`--upstream` 指向符合固定提交的本地 checkout。安装器不自动克隆上游，也不修改上游文件。单文件程序构建：

```powershell
.\scripts\build_exe.ps1 -Upstream "D:\path\to\unlock"
```

### 安全边界

- 不自动执行 WBI。WBI 是对 `/dev/nflasha5` 前 512 字节的 eMMC 写入；本次操作在无 Pico/BootROM 恢复路线的条件下由机主明确授权执行，属于偏离上游恢复路线要求的操作。不要重复执行。
- 写入前必须完成整盘备份、第二份逐字节备份、连接稳定性测试和保留性检查。
- 写入失败、超时或回读不一致时，状态标记为 `UNKNOWN`，禁止开新会话重试；先做只读复核。
- 不包含 Sony 的 `ud_wbi_drop.elf`、固件、BootROM dump、设备备份或密钥。
- `runs/` 与上游会话目录可能包含设备标识和完整库快照，保持私有，不要提交或公开。
- 修改相机固件可能影响保修；5 GHz 使用受当地法规约束。

### 扩展与集成

当前工具属于受控引导式安装器，不是无人值守的一键刷写。WBI 和写入确认保留人工步骤。后续同机型功能应以独立模块接入，建议遵循以下边界：

- 模块放在 `src/zve10_installer/steps/`，独立完成只读预检、写入、终检和回读；
- 每个模块定义自己的状态阶段、门禁、备份范围、确认字符串和失败处理；
- 新增写入前必须证明原厂状态、目标文件哈希、分区挂载和回滚材料；
- 第三方代码或工具需单独审查许可、来源和哈希，不直接合并未经验证的二进制；
- 新增模块必须附带离线测试，并在工厂状态相机上完成端到端验证后才能标记为可用；
- WBI、BootROM、DSP 等高风险路径不纳入自动流程。

### 文档与许可

- [研究记录](docs/RESEARCH.md)：5 GHz 解锁、安装器门禁、快门声音实验、失败与修正。
- [安装器说明](docs/INSTALLER.md)：GUI 流程、CLI 命令、驱动、备份与验收。
- [测试者说明](docs/TESTER-GUIDE.md)：只读测试、诊断包和禁止回传的数据。
- [变更记录](CHANGELOG.md)：版本历史和 2026-11-17 真机结果。

本仓库代码采用 MIT 许可。上游项目、Sony-PMCA-RE 和 Zadig 的许可与固定提交见 [NOTICE.md](NOTICE.md)。`cokeenet/zve10-qemu` 采用 PolyForm Noncommercial 1.0.0；本仓库仅引用其公开的格式事实，未复制其代码。

## English

### Scope and results

| Area | Result |
|---|---|
| 5 GHz menu | A single-byte patch to `CautionConfig.so`, three Backup properties, and WBI invalidation were completed on one ZV-E10 2.03. After a cold boot, `Page1=TypeNB/5` and the camera menu exposed the 5 GHz band option. RF link behavior was not tested. |
| Installer | Source, state machine, gates, double backup, preservation checks, runtime byte check, and a five-step GUI are implemented. Read-only `verify` passed on hardware; `install` has not been validated end-to-end on a factory-state camera. |
| Shutter sound | Writes to all nine `avsystemsound` slots, per-file readback, cold-boot persistence, and one-command restore passed on hardware. The camera did not play the custom audio; the shutter sound on this firmware does not come from these files. |
| Offline tests | 43 pytest cases pass, covering gates, state transitions, backup, stability, preservation, the sound codec, the sound service actions, and restore preflight. |

### Repository layout

```text
src/zve10_installer/       installer, CLI, GUI, state machine, gates, sound codec/server
tests/                     offline tests
packaging/                 PyInstaller specifications and frozen entry points
scripts/                   environment bootstrap and build scripts
compat/windows/            uid/chown/pwd and libusb compatibility shim
docs/INSTALLER.md          installer manual (Chinese)
docs/TESTER-GUIDE.md       tester procedure and log requirements (Chinese)
docs/RESEARCH.md           full research record (Chinese)
```

### Build

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
```

`--upstream` must point to a local checkout at the pinned commits. The installer does not clone or modify upstream files. To build the single-file programs:

```powershell
.\scripts\build_exe.ps1 -Upstream "D:\path\to\unlock"
```

### Safety model

- WBI is never automatic. It writes the first 512 bytes of `/dev/nflasha5`; the operation recorded here was authorized by the device owner without a Pico/BootROM recovery path, which deviates from the upstream recovery-route requirement. Do not repeat it.
- A write requires a full backup, a second byte-compared backup, a read-only stability test, and preservation checks.
- Timeouts, short reads, or hash mismatches mark the run `UNKNOWN`; no new session is opened to retry before a read-only review.
- Sony `ud_wbi_drop.elf`, firmware, BootROM dumps, device backups, and keys are not included.
- `runs/` and upstream session directories may contain device identifiers and full library snapshots. Keep them private.
- Firmware modification may affect warranty; 5 GHz operation is subject to local regulations.

### Extending the framework

The current tool is a guided, gate-enforced installer, not an unattended one-click writer. WBI and write confirmations remain manual. Additional same-model features should be integrated as independent modules:

- place each feature under `src/zve10_installer/steps/` with its own read-only preflight, write, final inspection, and readback;
- define per-module state stages, gates, backup scope, confirmation string, and failure handling;
- prove the factory state, target hashes, partition mount identity, and rollback material before any write;
- review the license, source, and hash of third-party code or binaries; do not merge unverified binaries;
- require offline tests and end-to-end validation on a factory-state camera before marking a module usable;
- keep WBI, BootROM, and DSP paths outside the automatic flow.

### Documentation and license

- [Research record](docs/RESEARCH.md) (Chinese): 5 GHz unlock, installer gates, shutter-sound experiment, failures and corrections.
- [Installer manual](docs/INSTALLER.md) (Chinese): GUI flow, CLI commands, driver, backup, acceptance.
- [Tester guide](docs/TESTER-GUIDE.md) (Chinese): read-only testing, diagnostic bundle, prohibited data.
- [Changelog](CHANGELOG.md): version history and the 2026-11-17 hardware result.

The code in this repository is MIT-licensed. Upstream projects, Sony-PMCA-RE, and Zadig notices and pinned revisions are in [NOTICE.md](NOTICE.md). `cokeenet/zve10-qemu` is PolyForm Noncommercial 1.0.0; only its published format facts are cited, and no code was copied.
