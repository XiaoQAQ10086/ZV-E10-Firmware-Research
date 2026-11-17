# 测试者说明（ZV-E10 5GHz 安装器）

> 本工具只针对 **ZV-E10 一代，固件 2.02 / 2.03**。
> 当前版本的写入路径还没有在工厂状态相机上端到端验证过；请先做只读测试。

## 测试环境

- Windows 10/11 x64；
- 相机 USB 连接设为 **Mass Storage（海量存储器）**；
- 用支持数据传输的 USB-C 线，直接插电脑，尽量不经过 Hub；
- 已绑定 WinUSB（未绑定时程序里有“安装驱动/驱动恢复”）；
- 相机电量至少 50%。

## 只读测试（安全，推荐先做）

```powershell
.\ZV-E10-Installer.exe
```

在 GUI 里按顺序：

1. **环境检查**（Doctor）
2. **开始检查**：如果相机是工厂状态，这一步会做稳定性测试 + 整盘备份 + 第二份备份；如果是已刷过的相机，会明确拒绝刷入；
3. **验收检查**（Verify）——已刷过的相机会读取补丁、属性、`Page1` 和运行期字节；
4. 打开 **技术详情 / 高级** → **导出诊断包**。

也可以只用命令行：

```powershell
.\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
.\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\zve10-installer.exe verify --upstream "D:\path\to\unlock" --runtime-check
.\zve10-installer.exe diagnose --upstream "D:\path\to\unlock" --runs-dir "D:\path\to\runs"
```

## 工厂相机的写入测试（可选，需机主明确同意）

写入会修改相机内部文件；当前版本尚未在工厂相机上验证。只有机主明确同意时才做。

需要：

- 一个空的**第二份备份目录**（建议另一块磁盘）；
- 相机电量 ≥50%，写入期间不断电、不拔线；
- 机主已知晓：写入失败可能需要送修，且本机没有硬件恢复路线。

步骤：

1. 冷启动相机（关机 → 灯灭 → 拔线 → 取电池 30 秒 → 开机 → Mass Storage → 插线）；
2. 打开 GUI → 准备页填写电量、选择第二份备份目录、勾选区域；
3. 开始检查 → 检查通过 → 开始刷入（逐字输入 `PATCH ZV-E10 2.03`）；
4. 冷启动 → 验收；
5. 导出诊断包。

## 需要回传的内容

优先回传 **诊断包 zip**（GUI 或 `diagnose` 命令生成）。它包含：

- 环境信息、`doctor` 结果；
- 最近几次运行的 `state.json`、`run.jsonl`、`summary.json`、`serve.out/err`；
- 不包含 `.bin` 备份、`.so`、固件、Sony 工具或原始序列号。

另外请文字说明：

- 相机型号、固件版本、区域（中国大陆 B=2/C=22？）；
- Windows 版本、驱动状态；
- 卡在哪一步、屏幕提示、错误文字；
- 如果是菜单/功能测试，实际看到什么。

## 不要回传

- 完整 eMMC 备份、`private/` 目录；
- 相机序列号、密钥、MAC；
- Sony 的 `ud_wbi_drop.elf` 或固件包。

诊断包可能包含本机路径和会话日志；公开分享前请先检查。
