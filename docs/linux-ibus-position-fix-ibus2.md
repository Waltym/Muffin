# Muffin 0.7.9：候选框位置同步修复记录（ibus2）

> 本文保留 ibus2 的修复过程。后续 ibus3 保留本修复并增加默认高亮背景，当前打包脚本已升级，详见 [ibus3 修复记录](markdown-highlight-fix-ibus3.md)。

日期：2026-10-31。

## 1. 交付结果

- 应用版本：Muffin 0.7.9。
- 新包版本：`0.7.9-1+ibus2`，可直接升级此前的 `0.7.9-1+ibus1`。
- 安装包：`muffin_0.7.9-1+ibus2_amd64.deb（下载目录）`。
- 大小：46,709,968 字节，约 44.5 MiB。
- SHA256：`7080763de14ef22865097ea47de12690f18ecde24ac71bf56bcd6ef71e9df4dd`。
- 已生成并验证安装包；没有执行系统安装，当前已安装的 ibus1 版本保持不变。

## 2. 原因与修复策略

ibus1 补齐 Qt IBus 插件后中文输入恢复，但 Muffin 编辑器只实现了光标位置查询，缺少光标移动、预编辑、滚动和窗口重排后的输入法位置更新通知。

本次采用 **官方编辑器二进制 + 编译的应用私有 IBus 位置适配插件**，没有重新编译编辑器，也没有改动编辑、解析或文档保存算法。相较完整重建编辑器及其依赖，这种策略只需要已有的 C++ 编译器与匹配的 Qt SDK，不需要安装新依赖。

适配插件通过 Qt 标准输入法插件入口加载原版 Qt 6.11.1 IBus 实现，返回原版输入上下文，继续由原版处理按键、选词和文本提交；新增观察器只补齐候选框定位通知。

## 3. 具体实现

新增源码：

```text
src/platform/ibus/MuffinIBusPlugin.cpp
src/platform/ibus/MuffinImePositionTracker.h
src/platform/ibus/muffin-ibus.json
```

位置观察器：

1. 仅在焦点为 `muffin::EditorView` 或 `muffin::VirtualSourceEdit` 时工作，不介入其他应用或普通输入控件。
2. 观察光标相关按键、鼠标、预编辑、绘制、滚动引发的重绘、布局、窗口尺寸/位置、全屏及 DPI 变化。
3. 通过零延时单次定时器合并同一事件循环内的重复请求，等编辑器处理完事件、布局更新后读取坐标。
4. 比较局部光标矩形、屏幕位置、焦点窗口和缩放因子；无变化时不重复发送。
5. 焦点/预编辑变化时强制刷新；只读或无有效矩形时不发送错误位置。
6. 调用 `QInputMethod::update(Qt::ImCursorRectangle)`，由原版 Qt IBus 继续完成坐标变换及 `SetCursorLocation` 通信。

没有后台轮询，没有固定像素偏移，没有手动重复缩放，也不消费按键、不修改文本。

### 安装布局

```text
/usr/lib/muffin/platforminputcontexts/libibusplatforminputcontextplugin.so
    新编译的适配插件，RUNPATH=$ORIGIN/..

/usr/lib/muffin/platforminputcontexts/upstream/libibusplatforminputcontextplugin.so
    原版 Qt 6.11.1 IBus 插件，仅调整 RUNPATH=$ORIGIN/../..

/usr/lib/muffin/libQt6DBus.so.6.11.1
    匹配的 Qt D-Bus 运行库，沿用上一版

/usr/share/doc/muffin/ibus-position-source/
    随包提供适配源码、元数据和本地打包脚本
```

Qt 插件自动加载适配层；**生产包不需要也没有设置 `LD_PRELOAD`**。应用启动器与输入法环境处理沿用上一版，不修改系统 Qt、全局输入法配置或用户笔记。

## 4. 构建

扩展了 `scripts/package_linux_deb.py`：

- 使用固定 SHA256 的官方 Muffin 及 Qt 6.11.1 归档。
- 使用同版本 SDK 头文件与 `moc 6.11.1`，通过系统已有 `g++` 编译适配插件。
- 编译开启 `-Wall -Wextra -Werror`、链接开启 `-z defs`。
- 包含适配源码哈希、插件哈希、编译器信息与上游归档哈希，记录在包内 `build-inputs.json`。
- 依赖扫描覆盖全部私有库及嵌套插件，避免误依赖系统不同版本的 Qt。
- 对所有包内 ELF 执行 `ldd -r`，拒绝缺失运行库和未解析符号。
- 使用 root 所有权元数据生成 `.deb`，构建不需要 root。
- 拒绝覆盖同名既有安装包；ibus1 安装包仍保留。

重打包命令（源码目录下；可通过环境变量 `PYTHON` 指定现有 Python 解释器，默认使用 `python3`）：

```bash
${PYTHON:-python3} scripts/package_linux_deb.py \
  --bundle-archive local/downloads/Muffin-v0.7.9-linux-x64.tar.gz \
  --qtbase-archive local/downloads/qtbase-6.11.1.7z \
  --qt-sdk local/qt-sdk \
  --output-dir packages/ibus2-rebuilt
```

## 5. 实际验证

### 5.1 自动定位回归

新增测试驱动：

```text
tests/packaging/ImePositionAcceptance.cpp
tests/packaging/run_ime_position_acceptance.py
```

测试驱动在独立临时文档和独立配置中运行，不向其他应用发送全局按键。驱动本身不调用输入法更新接口，而是记录程序是否自动发出位置更新，并与当前光标几何比较。诊断驱动仅在测试进程中通过 `LD_PRELOAD` 加载，不进入交付包。

| 场景 | 旧版 ibus1 | 新包默认缩放 | 新包额外 1.5 倍缩放 |
|---|---|---|---|
| 普通窗口、左右/上下移动 | 失败 | 通过 | 通过 |
| 滚动、移动窗口 | 失败 | 通过 | 通过 |
| 最大化、全屏、全屏内移动 | 失败 | 通过 | 通过 |
| 预编辑和取消预编辑 | 失败 | 通过 | 通过 |
| 源码模式焦点、移动和滚动 | 仅焦点切换通过 | 全部通过 | 全部通过 |
| 空闲绘制不重复发送 | 校验失败（已有定位不同步） | 通过 | 通过 |

总计：

- 旧版：15 项中 14 项失败，成功复现通知缺失。
- 新包默认缩放：15/15 通过；Qt IBus 日志记录 16 条位置发送。
- 新包设置 `QT_SCALE_FACTOR=1.5`：15/15 通过；记录 18 条位置发送。

日志与 JSON 结果：

```text
local/ibus2-baseline-regression/
local/ibus2-package-acceptance/
local/ibus2-package-hidpi-acceptance/
```

### 5.2 真实 ibus-rime 输入

对解包后的新版程序，使用原生 X11 测试按键输入拼音并选词，不是粘贴或直接注入中文：

- 所见即所得模式：Rime 日志记录提交“你好”，UTF-8 文件保存成功，并有光标位置发送。
- 源码模式：同样记录提交“你好”并保存成功，同时发送新位置。
- 测试对按下事件检查窗口焦点，窗口失焦则中止；退出使用测试进程结束方式，避免退出快捷键造成修饰键释放不完整。

证据文件：

```text
local/gui-tests/ibus2-real-render/
local/gui-tests/ibus2-real-source/
```

所见即所得测试的 Rime 上下文初始为英文状态，因此首次保存了 `nihao`；在该测试上下文切换中文状态后，成功提交并保存“你好”。这不是将拉丁字母结果误计为中文测试通过。

### 5.3 其他检查

- 9 项打包单元测试通过。
- 安装包全部 ELF 的运行库及符号检查通过。
- 启动器 shell 语法检查通过，desktop 文件无错误（仅有可补充 Utility 分类的提示）。
- 包哈希校验通过，版本号严格高于 ibus1。
- `apt-get --simulate install` 确认为从 ibus1 升级到 ibus2，无新增依赖、无删除包。
- 未运行上游编辑器全量 Conan/CTest；编辑器二进制未重编译，本次验证针对新增适配插件和实际交付包。

## 6. 安装与回退

**先退出所有 Muffin 窗口，再执行升级；无需先卸载旧版。将 `/path/to/downloads` 替换为安装包所在目录。**

```bash
cd /path/to/downloads
sha256sum --check muffin_0.7.9-1+ibus2_amd64.deb.sha256
sudo apt install ./muffin_0.7.9-1+ibus2_amd64.deb
```

升级后重新启动 Muffin。建议新建临时笔记，在普通、最大化、全屏状态下输入中文、换行及滚动，确认候选框位置符合实际使用习惯。

如需回退，退出 Muffin 后由用户执行（旧包仍在下载目录）：

```bash
sudo apt install --allow-downgrades ./muffin_0.7.9-1+ibus1_amd64.deb
```

回退会恢复旧版行为，包括候选框定位缺陷；不会删除用户笔记。以上安装/回退命令均未代用户执行。

## 7. 范围与限制

- 已测环境：Debian 13 amd64、GNOME X11、ibus-rime。
- Wayland、多显示器跨屏切换、其他发行版和架构未验证。
- 验证了输入法位置发送与编辑器当前查询坐标一致，但未对 GNOME 可见候选面板进行像素距离测量。
- 没有修改上游预编辑文本排版或光标矩形算法；超长拼音跨行、复杂表格、代码块横向滚动等细节仍需扩展回归，不能宣称所有 IME 边界情形已覆盖。
- 上游 `Could not create collator: 4` 警告未在本次处理。
