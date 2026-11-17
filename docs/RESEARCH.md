# ZV-E10 2.03 固件研究记录

记录日期：2026-11-17

设备：Sony ZV-E10（ILCE-ZV-E10），系统版本 `30110_06.2026060501`（2.03）

主机：Windows 11 x64，Python 3.12

## 1. 范围与结论

本记录覆盖三项工作：

1. 恢复 ZV-E10 2.03 的 5 GHz 频段菜单；
2. 将该过程实现为带门禁的安装器；
3. 评估通过替换 `/usr/share/avsystemsound/*.bin` 修改快门声音的可行性。

第 1 项在单台相机上完成写入、回读和冷启动验收，菜单出现 5 GHz 选项；实际射频工作未测试。第 2 项的只读路径在实机通过，写入路径未在工厂状态相机上完成端到端验证。第 3 项的文件写入、持久化和回退在实机通过，但相机没有播放替换后的声音，因此该路线不能实现自定义快门声。

## 2. 环境与工具链

- 相机 USB 模式：Mass Storage；Windows 驱动：WinUSB。
- 服务模式传输：Sony-PMCA-RE；2.03 使用 toolkit 的 Jiritsu 后端。
- 上游固定提交：
  - 主仓库 `9def1681ee20a88f26daaf7ae43f4dbc51b43b2d`
  - toolkit `373bd482f9ef4e54ecaf5faf00e0afcbb4f041de`
  - Sony-PMCA-RE `a82f5baaa8e9c3d9f28f94699e860fb2e48cc8e0`
- 安装器不修改上游文件。服务会话、请求队列、认证、文件控制和 Jiritsu 上传均由上游实现。
- Windows 需要兼容垫片处理上游的 `uid`、`chown`、`pwd` 和 libusb DLL 查找；垫片位于 `compat/windows/sitecustomize.py`。

## 3. 5 GHz 菜单解锁

### 3.1 前置检查

只读检查通过 FileControl 读取以下事实：

| 项目 | 值 |
|---|---|
| 目标文件 | `/usr/lib/CautionConfig.so` |
| 大小 | 17,694,160 字节 |
| 工厂 SHA-256 | `5ad8746a229da259fe00b297e8f897d682f7ae9a13393025b3d1c95a808e68d7` |
| `/usr` 挂载 | `/dev/nflasha15`，ext2，只读 |
| Backup 属性 | `0x01071C54=00`、`0x00A5000B=09`、`0x00A5000C=09` |

读取 `/setting/Backup.bin` 和 `/setting/Backup.bak` 作为属性快照。整个文件读取完成后计算哈希，不使用短读或缓存值。

### 3.2 单字节补丁

补丁位于 `/usr/lib/CautionConfig.so` 偏移 `0xD778E4`：

```text
0x20 -> 0x1B
```

写入通过 toolkit 的 Jiritsu SET_FILE2 上传固定哈希的 `patch.arm`，临时 remount `/usr` 为可写，由该程序原位写入一个字节并 fsync、回读，然后 remount 只读并删除临时文件。终检结果：

| 项目 | 值 |
|---|---|
| 补丁后 SHA-256 | `14f42cc09ee1b9ddde5352482c13b68e5a5e97d9d79e8456087b5e0b7af6ff6a` |
| 大小 | 17,694,160 字节 |
| 唯一差异 | `0xD778E4` |

未使用 `cp` 覆盖已加载的 `.so`。上游文档记录该操作可能因空间不足截断文件；本次使用不截断的写入程序。

### 3.3 Backup 属性

三个属性按以下值写入：

| 属性 | 原值 | 新值 |
|---|---|---|
| `0x01071C54` | `00` | `01` |
| `0x00A5000B` | `09` | `02` |
| `0x00A5000C` | `09` | `16` |

写入后重新读取完整 Backup 数据库，确认目标属性为 `01/02/16`，且除写入期间已变化的运行时计数器外，没有其他属性变化。

### 3.4 WBI 失效

补丁和属性完成后，`Page1` 仍为 `TypeRK/4`，表示相机使用旧的 warm-resume 缓存页。WBI 失效通过 Sony 官方 `ud_wbi_drop.elf` 完成：

| 项目 | 值 |
|---|---|
| 工具大小 | 6,200 字节 |
| 工具 SHA-256 | `f2a5b27a0c11d55a612d61e61e82c55278efb744052ecb8ec2cbbd8851d0ea6e` |
| 目标 | `/dev/nflasha5` 前 512 字节 |
| 分区读取大小 | 62,914,560 字节 |
| 写入前 SHA-256 | `aa584ec93b17f786e6ffbdfe732ce351a17d3219119f0c549741999eea4832e5` |
| 写入后 SHA-256 | `2e78fd8a55186d1b28c688a96fee2a812d357bc40520408fc8cffea9389787e2` |
| 工具输出 | `[UD_WBI_DROP] /dev/nflasha5 wbi_drop` |

写入前后各做一次完整 60 MiB 读取并逐字节比较，确认只有前 512 字节被清零，其余字节不变。WBI 写入后 token 被消费，临时文件清理完成。

本次 WBI 写入没有 Pico/BootROM 恢复路线，属于机主明确授权下的偏离操作。上游要求先具备恢复路线；该要求在本机上无法满足。WBI 回刷恢复未实测，不要重复执行 WBI。

### 3.5 冷启动验收

关机、断开 USB、取电池 30 秒、重新开机、进入 Mass Storage 后，只读 `inspect` 与 `boot-check` 结果：

- `CautionConfig.so` SHA-256 仍为 `14f42cc0…`；
- Backup 属性仍为 `01/02/16`；
- `Page1` 类型为 `TypeNB`，项目数为 5；
- 相机菜单 `Network → Wi-Fi Settings → Frequency Band` 出现 2.4 GHz / 5 GHz 选项。

实际 5 GHz 关联、吞吐和信道测试未进行。菜单出现不等于射频链路已验收。

## 4. 受控安装器

### 4.1 设计目标

安装器不重新实现 USB、队列、认证、Backup 或 Jiritsu 协议，只在上游之上增加状态机、门禁、证据保存和用户确认。写入前必须满足条件，条件不满足时拒绝继续；写入后任何超时、短读或哈希不一致都进入 `UNKNOWN`，不自动重试。

### 4.2 状态机与门禁

主要阶段：

```text
CONNECTED -> PREWRITE_INSPECTED -> SCOPE_CONFIRMED -> BACKUP_DONE
          -> PATCHED -> PROPS_DONE -> INSTALLED -> CLOSED
```

门禁包括：

- 相机型号与系统版本两次一致；
- `CautionConfig.so` 大小与工厂/已补丁哈希；
- `/usr` 为 `/dev/nflasha15` ext2 只读；
- 属性基线 `00/09/09` 或已安装状态 `01/02/16`；
- 至少 120 秒只读稳定性测试，两次读取的库哈希与属性一致；
- 整盘备份完成并通过上游 `manifest/sums`；
- 第二份空目录备份逐字节比较；
- 写入期间非目标 Backup 属性不变；
- 关闭前 teardown 标志完整。

### 4.3 备份与证据

整盘备份使用上游 `raw-backup`，默认 4 MiB 块。2.03 上约 15 分钟。会话空闲超时 1 小时，活跃备份不消耗空闲预算。第二份备份必须位于空目录，复制后使用 `filecmp` 逐字节比较；目录为空、包含路径或比较失败都拒绝写入。

证据目录 `runs/<时间>-<类型>-<id>/` 保存 `state.json`、`run.jsonl`、`summary.json`、会话日志和快照路径。`runs/` 不进入仓库。

### 4.4 保留性检查

写入前读取完整 Backup 数据库，记录所有属性。准备期间已经变化的运行时计数器允许在安装后再次变化；其他属性必须保持不变。目标属性按预期变为 `01/02/16`。任何额外变化都会使验收失败并要求复核。

### 4.5 运行期字节检查

`verify --runtime-check` 从 `/proc/<pid>/maps` 找到覆盖文件偏移 `0xD778E4` 的映射，再通过 `/proc/<pid>/mem` 读取加载后的字节，期望 `0x1B`。该检查使用带诊断写标志的会话，因为只读 shell 允许列表不允许 `/proc` 管道；会话不发送写命令。

### 4.6 机身标识

Backup 序列号属性 `0x00E70003` 读取后只保存截断 SHA-256，不保存原始序列号。用于判断安装与验收是否为同一机身。仓库不包含任何机身标识值。

### 4.7 GUI 与驱动

GUI 为五步向导：准备、检查、刷入、冷启动、验收。准备页检查相机、固件、Mass Storage、WinUSB、区域、电量和第二份备份目录。驱动助手内置 Zadig 2.9（GPLv3，独立程序，不链接进安装器）；仓库不包含该二进制。驱动恢复通过设备管理器卸载设备并恢复 Windows 默认连接。

### 4.8 验证状态

| 项目 | 状态 |
|---|---|
| 只读 `inspect` / `verify` | 在实机通过 |
| `install` 写入 | 代码、门禁和离线测试完成；未在工厂状态相机上端到端验证 |
| WBI 拒绝路径 | `already-invalid` 已实测；有效 WBI 的 drop 已在本机执行 |
| 稳定性、双备份、保留性、运行期检查 | 离线测试通过；部分路径待工厂相机验证 |
| 驱动安装 | 未在“驱动未绑定”机器上实测 |

## 5. 快门声音实验

### 5.1 文件格式

ZV-E10 的快门音效位于 `/usr/share/avsystemsound/*.bin`，不是 WAV/MP3。格式为 24 kHz、32 字节一块的 ADPCM：

- 每块 32 字节，编码 31 个样本；
- 每块包含 predictor、shift 和残差；
- 解码递推：`previous = residual * (1 << shift) + (predictor ? 15/16 : 0) * previous`；
- 单个声音文件最大 24,832 字节，约 1 秒。

`beeplist.txt` 将 BEEP_ID 映射到文件。快门相关槽位包括 `Dslr_Emnt_Shutter_Ka/Sha/Sha2/Sha3/Sha4` 和 `Dslr_Emnt_10FPS_Kasha/Kasha2/Kasha3/Kasha4`，共 9 个。

格式事实来自 `cokeenet/zve10-qemu` 的公开研究记录。该仓库采用 PolyForm Noncommercial 1.0.0；本项目的编解码为独立实现，未复制其代码。

### 5.2 编解码实现

`src/zve10_installer/sound_codec.py` 实现：

- 严格 PCM WAV 输入，1/2 声道，8/16/24/32 位，8–96 kHz，≤1 秒，≤5 MB；
- 降为单声道，使用 Hann 窗 sinc 低通重采样到 24 kHz；
- 每 31 个样本选择最小平方误差的 shift，predictor 置 0；
- 补齐到 62 样本的整数倍并输出 32 字节块，最大 24,832 字节；
- 解码 BIN 生成预览 WAV。

原厂 `Dslr_Emnt_Shutter_Sha.bin` 为 1,216 字节，解码得到 1,178 样本、49.083 ms；重新编码后仍为 1,216 字节，SHA-256 `45f121216f1b29d593aa76e9a1b1cb139186a5ca55e96d706244deefb93b4fba`。原厂哈希为 `957ae8939f66bff6fdc1810cf854dbed51306d34cf6c8838e944bb5ed78be3fd`。

### 5.3 写入路径

上游 `wifi.py` 没有任意文件读写的结构化动作。本项目增加 `src/zve10_installer/sound_server.py`，在服务进程中替换 `REQUEST_HANDLER`，只接受 `sound-read` 和 `sound-write`，不修改上游文件。

写入流程：

1. 读取目标文件并核对当前 SHA-256；
2. 保存 `.before` 备份；
3. 通过 Jiritsu SET_FILE2 上传替换文件并完整回读；
4. 确认 `/usr` 为 `/dev/nflasha15` ext2 只读；
5. remount 为可写并再次确认挂载状态；
6. 写入同目录隐藏临时文件，`chmod 644`、`sync`、回读临时文件；
7. 使用 `busybox mv` 同目录原子替换；
8. 回读目标文件，逐字节一致；
9. `finally` 清理临时文件、remount 只读并复核。

上游服务的请求队列拒绝大于等于 4,096 字节的请求。24 KB 音频不能放入 JSON 请求体，因此替换数据先写入会话目录的 `sound-<hash>.bin`，请求只携带文件名；服务端校验文件名格式和大小后读取。

### 5.4 对照实验

第一次写入只替换 `Dslr_Emnt_Shutter_Sha.bin`，使用原厂声音的重新编码版：

| 项目 | 值 |
|---|---|
| 写入前 | `957ae8939f66…` |
| 写入后 | `45f12121…` |
| 大小 | 1,216 字节 |
| 回读 | 一致 |
| 冷启动后 | 仍为 `45f12121…` |

冷启动后声音没有变化。该结果符合预期，因为对照文件就是原厂音频的重新编码版；它证明写入通道和持久化正常，但不能证明相机播放的是这个文件。

### 5.5 全部槽位实验

将一段 0.981 秒、24 kHz 单声道的自定义音频写入全部 9 个槽位：

| 项目 | 值 |
|---|---|
| BIN 大小 | 24,320 字节，760 块 |
| SHA-256 | `ec8b789f8e1419655e0e25cfb27e5e502ef22556ad9c53a25d30edd3504b8cfe` |
| 峰值 | -5.91 dBFS |
| 回读 | 9/9 一致 |
| 冷启动后 | 9/9 仍为自定义哈希 |

冷启动后快门声仍为原厂声音，没有播放自定义音频。9 个槽位全部替换后仍无变化，说明该固件的快门声不来自这些文件。可能的原因是 beep type 指向其他数据源，或声音在 DSP/`av-cam.bin` 侧合成。公开研究对“全部替换仍无效”的判断与此一致。

### 5.6 回退

`sound-restore-all` 从 `sound-inspect` 保存的 `original/` 目录读取 9 个原厂文件，打开相机会话前先校验全部文件存在且哈希匹配官方 2.03 镜像，再逐个写回。已是原厂的文件跳过。回退后冷启动，9 个文件全部恢复原厂哈希。

本次实验已完成回退，冷启动后 `sound-inspect` 显示 9/9 `matches_image: true`。

### 5.7 结论

- 文件替换、回读、冷启动持久化和一键回退均正常；
- ZV-E10 2.03 不将这些 `avsystemsound` 文件作为快门声源；
- 更换其他音频文件预计无效；
- 不应继续修改 DSP/`av-cam.bin`。该路径风险高于文件替换，且没有恢复路线。

## 6. 失败与修正

### 6.1 Jiritsu 临时文件守卫误报

安装器的临时文件守卫在会话启动后检查 `/tmp/jiritsu`，原本将 `libJit.so`、`run.sh`、`out.txt` 视为残留。实际这三个文件由 Jiritsu 后端在 `start()` 时创建，并在 `close()` 时删除。守卫在 `start()` 之后运行，导致每个合法 2.03 会话都被拒绝：

```text
error: temp_guard: leftover temporary files in /tmp/jiritsu: libJit.so, out.txt, run.sh
```

修正：守卫只检查上游上传的 `zve10-wifi-*` 残留。Jiritsu 后端自身在启动时已经拒绝已存在的 loader workspace，不需要在守卫中重复检查这三个名字。该修正同时解除 `install` 在 2.03 上的阻塞。

### 6.2 `SoundSession.write` 属性遮蔽

`SoundSession.__init__` 使用 `self.write = write` 保存写模式，覆盖了同名的 `write()` 方法。首次真实写入时抛出：

```text
TypeError: 'bool' object is not callable
```

异常发生在发送 `sound-write` 请求之前，相机没有被写入。修正：标志改为 `write_mode`，并增加测试断言 `write()` 仍可调用。

### 6.3 4 KB 请求上限

声音替换最初把 24 KB 数据放入 JSON 请求。上游服务在扫描请求文件时丢弃大于等于 4,096 字节的文件，客户端只能等待超时。修正：数据写入会话目录的 `sound-<hash>.bin`，请求只包含文件名；服务端校验 `sound-[0-9a-f]{16}\.bin`、确认文件不是符号链接并限制大小。

### 6.4 冻结与传输问题

- PyInstaller 单文件入口曾因相对导入失败；`__main__.py` 改为先尝试相对导入，再回退绝对导入。
- 冻结服务缺少 `axmlparserpy`、`pycparser`、`certifi`、`six`、`comtypes`、`win32api`、`win32com`、`pythoncom`、`pywintypes` 等隐藏导入；补齐后服务可启动。
- 冻结服务曾把 `serve` 参数重复转发；`frozen.serve_upstream` 与 `sound_server.main` 改为仅在缺少时补 `serve`。
- 子命令后的 `--upstream` 曾被顶层解析器忽略；公共参数使用 `argparse.SUPPRESS` 保留顶层值。
- 相对 `runs` 路径曾导致会话目录落在上游目录下；`RunDir.create` 将基目录解析为绝对路径。
- 系统 Python 的 `axmlparserpy` 版本使用顶层 `import typeconstants`，与 PMCA 不兼容；构建和测试使用固定环境，冻结包写入正确版本。
- WBI prepare token 在会话关闭后失效，第二次准备需要新的会话；不得复用旧 token。
- 写入失败后不自动重试。状态标记为 `UNKNOWN`，先做只读检查。

## 7. 风险与限制

- 仅在单台 ZV-E10 2.03 上完成写入验证；2.02 和其他区域没有实机证据。
- 5 GHz 只验证了菜单出现，没有做关联、吞吐、信道和干扰测试。
- WBI 写入没有 Pico/BootROM 恢复路线，属于机主明确授权的偏离操作；WBI 回刷恢复未实测。
- `install` 写入路径尚未在工厂状态相机上端到端验证。
- `/usr` 为 ext2，无日志；断电或 eMMC 故障可能导致文件系统异常。声音写入采用临时文件加原子改名，降低截断风险，但不能消除该风险。
- 相机固件修改可能影响保修；5 GHz 使用受当地法规约束。
- 本项目与 Sony 无关，未获官方支持。

## 8. 复现

1. 准备符合固定提交的上游 checkout，见 [NOTICE.md](../NOTICE.md)。
2. 安装 Python 3.10+，执行 `pip install -e .`。
3. 运行 `zve10-installer doctor` 检查 USB、驱动和固定提交。
4. 只读运行 `inspect` 或 GUI 的只读检查，确认固件版本、库哈希、属性和 `/usr` 挂载。
5. 需要写入时，按 [INSTALLER.md](INSTALLER.md) 完成备份、稳定性测试、第二份备份和确认。
6. WBI 不属于自动流程；没有恢复路线时不要执行。
7. 快门声音写入与回退命令见 [INSTALLER.md](INSTALLER.md) 的声音章节。替换文件不会改变该固件的快门声。

## 9. 参考资料

- `dino2048/ZV-E10-5GHz-WiFi-Unlock`：5 GHz 解锁流程与固定提交。
- `dino2048/zv-e10-toolkit`：Jiritsu 后端、Backup、文件控制和终端服务。
- `Sony-PMCA-RE`：USB 服务模式传输。
- `cokeenet/zve10-qemu`：公开的 `avsystemsound` 格式研究。PolyForm Noncommercial 1.0.0；本项目未复制其代码。
- 对第三方相机工具的功能与安全设计审查：仅用于门禁、备份、诊断和运行期检查的工程对照，未复制代码或二进制。

## 10. 许可

本仓库代码采用 MIT 许可。第三方项目的版权与许可见 [NOTICE.md](../NOTICE.md)。Sony 的 `ud_wbi_drop.elf`、固件、BootROM dump 和设备备份不随本仓库分发。
