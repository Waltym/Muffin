# Muffin 0.7.9：IBus 输入修复与 Debian 打包记录

> 本文保留 ibus1 初次修复记录。后续候选框定位已在 ibus2 中修复，打包脚本也已增加 `--qt-sdk` 参数；当前安装及重建命令请以 [ibus2 修复记录](linux-ibus-position-fix-ibus2.md) 为准。

- 记录日期：2026-10-31。
- 上游项目：https://github.com/jstzwj/Muffin
- 应用版本：0.7.9；本地 Debian 包版本：`0.7.9-1+ibus1`。
- 修复目标：解决 ibus-rime 中文拼音输入不可用的问题，并提供便于安装的 `.deb` 包。
- 交付结论：所见即所得模式已实测中文输入和保存；已生成安装包，但没有执行系统安装。

## 问题现象与排查

用户此前安装使用 Muffin 时无法输入中文，日常使用的输入法为 ibus-rime。
本次检查时没有找到仍安装着的 Muffin 程序，因此另行获取官方 Linux 0.7.9 发行包作为复现与修复基线，不能认定它就是用户此前安装的具体版本。

本机检查确认 IBus 守护进程与 Rime 引擎正在运行，`ibus engine` 返回 `rime`。编辑器源码已有 `WA_InputMethodEnabled`、`inputMethodEvent` 和 `inputMethodQuery` 等输入法处理逻辑，因此优先排查发行包组件，而不是直接改动编辑器算法。

对原版发行包的检查结果：

1. 包内存在 Qt 平台插件，但没有 `platforminputcontexts` 目录。
2. `QT_DEBUG_PLUGINS=1` 启动日志显示程序查找输入法插件目录，却没有加载 IBus 插件。
3. 原包测试输入 `nihao` 后保存的是拉丁字母，未发生中文转换。
4. 检查 Conan Qt 配方，发现其默认关闭 D-Bus；Muffin 原有配置没有为 Linux 显式开启该选项。

尝试检查系统插件兼容性时，使用系统 Qt D-Bus 库配合包内 Qt 运行库执行 `ldd -r`，出现私有符号错误：

```text
undefined symbol: _ZN14QObjectPrivateC2Ei, version Qt_6_PRIVATE_API
```

因此没有采用“直接复制系统输入法插件”的方案，改为补齐与官方包匹配的 Qt 6.11.1 组件。

## 结论与适用范围

- 实机：Debian 13 amd64、GNOME X11、ibus-rime。
- 官方 Linux 0.7.9 包缺少 `platforminputcontexts`；原包启动时找不到 IBus 插件。
- Conan Qt 配方默认 `with_dbus=False`，也不会构建依赖 D-Bus 的 IBus 插件。
- 官方包捆绑 Qt 6.11.1，而系统是 Qt 6.8.2。混用系统 Qt D-Bus 库会出现 `QObjectPrivate` 私有符号缺失，不能简单复制系统插件解决。

## 实际交付方式

本包为 **官方二进制重新打包**，不是重新编译的 Muffin：

1. 保留官方 Muffin 0.7.9 编辑器及其私有 Qt 运行库。
2. 从 Qt 官方 6.11.1 SDK 补入 IBus 插件和 `libQt6DBus.so.6.11.1`。
3. 将插件已有 RUNPATH 从 `$ORIGIN/../../lib` 原位缩短为 `$ORIGIN/..`，解析到本应用私有运行库，不依赖 Conda 或构建目录。
4. `/usr/bin/muffin` 启动器只为当前应用处理 X11 IBus 环境和 fontconfig 默认配置，不改全局环境、不强制覆盖已指定的输入法。
5. 添加应用菜单、图标、Markdown MIME 声明、许可证与构建输入 SHA256。

输入来源和校验值在包内 `/usr/share/doc/muffin/build-inputs.json`。

### 关键安装布局

```text
/usr/bin/muffin                             # 启动器
/usr/bin/muffin-mmdc                        # Mermaid 命令行启动器
/usr/lib/muffin/Muffin                      # 官方编辑器程序
/usr/lib/muffin/libQt6DBus.so.6.11.1         # 补入的同版本 D-Bus 库
/usr/lib/muffin/libQt6DBus.so.6              # 指向上述文件的符号链接
/usr/lib/muffin/platforminputcontexts/
    libibusplatforminputcontextplugin.so    # 补入的 IBus 插件
/usr/share/applications/muffin.desktop      # 应用菜单入口
/usr/share/doc/muffin/                      # 说明、许可证与构建输入记录
```

### 输入来源与校验

官方 Muffin 发行包：

<https://github.com/jstzwj/Muffin/releases/download/v0.7.9/Muffin-v0.7.9-linux-x64.tar.gz>

```text
SHA256: e53f83505509d1c407dcdbee381f45662e1121fe995d2f3bee846fd50f624214
```

Qt 官方 SDK 归档：

<https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/qt6_6111/qt6_6111/qt.qt6.6111.linux_gcc_64/6.11.1-0-202605090529qtbase-Linux-RHEL_9_6-GCC-Linux-RHEL_9_6-X86_64.7z>

```text
SHA256: 1d6d82d765987d657d0df136fb347e98d6e29e99ef8d1cb433abf9f15c86ab6f
```

交付 `.deb`：

```text
文件名: muffin_0.7.9-1+ibus1_amd64.deb
大小: 46,695,816 字节（约 44.5 MiB）
SHA256: 2244e67e577041220d11b7018b68ea6d9ce2b7bf6c6eabcd06a75b76aa8e0686
```

## 文件

- `packages/muffin_0.7.9-1+ibus1_amd64.deb`
- `packages/muffin_0.7.9-1+ibus1_amd64.deb.sha256`
- `packages/muffin-linux-ibus-source.patch`
- `scripts/package_linux_deb.py`：带输入哈希校验、禁止覆盖已有 deb 的本地构建脚本。
- `tests/packaging/test_linux_deb.py`：标准库单元测试。
- `local/gui-tests/deb-render-native/`：解包后程序的实际中文输入测试文件及日志，不包含在 deb 内。

另已将 deb 和安装说明复制到用户下载目录。

## 源码修复（供后续从源码构建使用）

- `conanfile.py`：Linux 显式启用 Qt D-Bus。
- `CMakeLists.txt`、`cmake/MuffinDeploy.cmake`：所有 Qt 插件发现路径均包含 `platforminputcontexts`；Linux 发布包缺少 IBus 插件时直接报错，避免再次发布无中文输入的包。

没有更改编辑算法、文档格式或接口。这些源码改动本次未完整编译，也未运行上游全量 CTest；交付 deb 通过官方二进制补齐组件实现修复。

## 已执行验证

- Qt SDK 归档 SHA1 与官方校验文件一致；两份输入归档均锁定 SHA256。
- 包内全部 ELF 文件执行 `ldd -r`，无缺失库或未解析符号。
- Qt 插件调试日志确认 IBus 插件加载、实际连接运行中的 IBus。
- 在真实 X11 会话中通过原生 XTest 按键（不是粘贴或直接注入中文）输入 `nihao` 并选词，日志记录 `commit text: "你好"`，保存的 UTF-8 文件包含 `你好`。
- 安装包解包后程序返回 `Muffin 0.7.9`。
- Debian 依赖扫描包含私有库和插件，不错误依赖系统 Qt。
- `apt-get --simulate install`：当前系统只新增 `muffin`，无待补依赖；没有实际安装。
- 7 项打包单元测试通过；`git diff --check` 通过；启动器 shell 语法检查通过。
- desktop 文件验证无错误（有 TextEditor 分类可添加 Utility 的非阻断提示）。

## 验证限制

- 源码模式自动化输入未验证通过：窗口失焦后测试中止/输入未送达，不据此断言源码模式存在独立缺陷。所见即所得模式已确认真实 IBus 输入及保存。
- 未测试 Wayland、其他发行版、其他 CPU 架构或其他输入法。
- 上游程序仍输出 `Could not create collator: 4` 警告；此警告也存在于原包，未在本次调整无关的排序/ICU 实现。
- 未执行系统级安装/卸载，未修改 IBus/Rime 配置。

## 安装、验证与回退

安装包已保存至：

```text
muffin_0.7.9-1+ibus1_amd64.deb（下载目录）
```

可先校验文件，再由用户执行安装（将 `/path/to/downloads` 替换为安装包所在目录）：

```bash
cd /path/to/downloads
sha256sum --check muffin_0.7.9-1+ibus1_amd64.deb.sha256
sudo apt install ./muffin_0.7.9-1+ibus1_amd64.deb
```

安装后通过应用菜单或 `muffin` 命令启动。建议新建临时笔记，切换到 ibus-rime 中文状态，输入拼音、选择候选词、保存并重新打开；再手动检查源码模式中文输入。

如需移除本包，可由用户执行：

```bash
sudo apt remove muffin
```

本包不包含用户笔记；卸载命令不删除用户自行保存的 Markdown 文件。修复过程中没有安装依赖、修改系统 Qt、变更全局环境变量，也没有修改 IBus/Rime 配置，因此没有相关系统配置需要回滚。

## 重新打包

在源码根目录执行（不安装依赖、不修改 Python 环境）。可通过环境变量 `PYTHON` 指定现有 Python 解释器，未指定时使用 `python3`：

```bash
${PYTHON:-python3} scripts/package_linux_deb.py \
  --bundle-archive local/downloads/Muffin-v0.7.9-linux-x64.tar.gz \
  --qtbase-archive local/downloads/qtbase-6.11.1.7z \
  --output-dir packages/rebuilt

${PYTHON:-python3} \
  -m unittest discover -s tests/packaging -v
```

脚本要求当前已有 `7z`、`dpkg-deb`、`dpkg-shlibdeps`，仅输出本地包，不会自动下载或安装软件。
