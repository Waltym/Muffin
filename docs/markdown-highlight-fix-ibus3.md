# Muffin 0.7.9：高亮背景修复记录（ibus3）

> 后续 ibus4 保留高亮和输入法修复，并补齐大图等比适配。当前打包脚本已升级，详见 [大图修复记录](image-fit-fix-ibus4.md)。下文保留 ibus3 的历史记录。

日期：2026-10-31。

## 1. 交付

- 新版包：`muffin_0.7.9-1+ibus3_amd64.deb`。
- 保存位置：下载目录。
- 大小：46,710,448 字节，约 44.5 MiB。
- SHA256：`d9a0cca3552d37652f9147e1e23079aaf99606b6275b54bbcc247c7f74eaac92`。
- 可直接从 ibus2 升级；保留之前的 IBus 中文输入和候选框定位修复。
- 没有执行系统安装，没有改动正在运行的 Muffin、用户笔记、输入法配置或用户自定义主题。

## 2. 缺陷原因

`==文字==` 已正确解析为高亮节点，但 GitHub 等主题没有显式定义语义 `mark` 背景。文本格式层将背景绘制交给语义框后，基础 CSS 又没有提供 `mark` 的缺省背景，导致语法标记消失而底色缺失。

Night 主题自带 `mark` 背景，因此此前正常。问题不在高亮开关保存或定界符解析。

## 3. 源码修复

在 `resources/themes/document-base.css` 中增加一条基础规则：

```css
mark { background-color: #fff173; }
```

文档样式的合并顺序保持“基础样式在先、主题作者样式在后”，不使用 `!important`：

- 没有指定高亮颜色的主题得到默认浅黄色。
- Night 的 `#D3D40E` 保持不变。
- 自定义背景色继续优先。
- 自定义 `transparent` 仍被尊重，不强制补回黄色。

不修改解析算法、文本、上下标排版或输入法逻辑。

源码补丁：`packages/ibus3/markdown-highlight-default.patch`。

## 4. 本地发行包的补丁方式与安全检查

官方版本将基础 CSS 编译为 `libMuffinUi.so` 内的只读字符串，并非外置文件。本次没有重新编译整个编辑器，也没有在系统安装目录中直接改库。

打包脚本对解包后的副本执行严格校验的数据补丁：

1. 仅接受固定 SHA256 的原版 `libMuffinUi.so`。
2. 要求完整原始基础 CSS 在库中恰好出现一次。
3. 将该 CSS 开头 77 字节的注释替换为较短的默认规则及空白填充。
4. 保持文件大小、字符串长度、ELF 地址与偏移不变。
5. 对修改区域前后的全部字节做相等性校验；不修改机器指令。
6. 重复补丁、未知哈希或多个匹配字符串均拒绝处理。

实际审计结果：

```text
文件：libMuffinUi.so
文件大小：43,799,208 字节（未变）
CSS 注释区偏移：10,921,568
允许修改范围：77 字节
实际不同字节：68
该区域以外：全部逐字节相同

原始 SHA256：
a1c3fe544698f7a626f90c0eed7b81c34e1e506d1952ce3275e9b940165c3776

修复后 SHA256：
72512441c78a83c1787331b6f5e20c9cd1bf71272bc67394a0460e3d4d2731b2
```

同时对比 ibus2 和 ibus3 全部应用运行文件：**只有 `libMuffinUi.so` 发生变化**；编辑器主程序、解析核心、Qt 库、IBus 原版插件和定位适配插件均保持字节一致。

修改范围、新旧哈希、规则及基础 CSS 源文件哈希已记录在包内 `/usr/share/doc/muffin/build-inputs.json`。正常完整源码构建会直接使用新增规则，不需要这种二进制数据补丁。

## 5. 验证结果

验证对象是新 deb 解包后的程序，而非旧的系统安装。诊断助手重新链接到新包的库路径，避免误加载系统旧库。

### 5.1 编辑器实际渲染与主题覆盖

使用独立临时文档、独立配置，测试字号 20、缩放 120%，同时查看实际 PNG 预览及背景色像素：

| 场景 | 结果 |
|---|---|
| GitHub | 中英文高亮正常，默认色像素 3,780 个 |
| Newsprint | 正常，默认色像素 3,610 个 |
| Pixyll | 正常，默认色像素 6,376 个 |
| Whitey | 正常，默认色像素 5,974 个 |
| Night | 保留原配色；截图与 ibus2 基线逐像素完全一致 |
| 扩展关闭 | 不出现高亮底色，保留原始语法 |
| 设置里启用，再增量输入 | 原文立即高亮，后续输入的高亮也有效 |
| 自定义绿色 | 保留绿色，不被默认黄色覆盖 |
| 自定义透明 | 保持透明，不补画黄色 |

设置切换与增量输入测试中，默认色像素从 0 增至 3,780，再增至 5,538，验证不仅是初次打开文档时生效。

英文 `H~2~O`、`X^2^` 及中文上下标的格式与实际截图均正常，无上下标回归。

测试源码与结果：

```text
tests/packaging/MarkdownHighlightProbe.cpp
tests/packaging/check_highlight_results.py
local/ibus3-highlight-tests/acceptance-summary.json
local/ibus3-highlight-tests/*/probe.log
local/ibus3-highlight-tests/*/*.png
```

截图已实际读取检查，不只依据命令退出码判断效果。像素校验命令（可通过环境变量 `PYTHON` 指定现有 Python 解释器，默认使用 `python3`）：

```bash
${PYTHON:-python3} tests/packaging/check_highlight_results.py \
  --results-dir local/ibus3-highlight-tests \
  --baseline-night local/markdown-extension-tests/night/cursor-away.png
```

该检查默认拒绝覆盖已有结果 JSON；重做实验应使用新的结果目录。

### 5.2 输入法回归

针对新包重新运行原有自动定位验收：普通窗口、移动、滚动、最大化、全屏、预编辑和源码模式等 **15/15 项通过**。Qt IBus 日志记录 16 次定位发送，空闲绘制未产生重复通知。

结果：`local/ibus3-position-acceptance/result.json`。

本次未重新进行真实 Rime 选词测试；IBus 两个插件与 ibus2 字节一致，且上述位置回归通过，不能将其混称为再次实测了全部中文输入流程。

### 5.3 包与安全检查

- 13 项打包单元测试通过，新增覆盖修改区域约束、未知库拒绝、重复匹配拒绝、重复补丁拒绝。
- 包内全部 ELF 的 `ldd -r` 检查通过，无缺失库及未解析符号。
- 依赖扫描通过，不错误依赖系统不同版本的 Qt。
- 安装模拟确认为 ibus2 → ibus3 升级，无新增依赖、无删除包。
- deb SHA256 校验通过。
- 未执行上游全量 Conan/CTest，也未完整重新编译编辑器。

## 6. 安装

**先保存笔记并退出所有 Muffin 窗口，进入安装包所在目录后直接升级，无需卸载：**

```bash
sudo apt install ./muffin_0.7.9-1+ibus3_amd64.deb
```

安装后重新启动 Muffin，在开启高亮扩展的正文中输入：

```markdown
这里是 ==中文高亮== 和 ==Highlight==。
```

不要将示例本身放在代码块内测试。旧包仍保留，必要时可由用户退出程序后显式降级回 ibus2。

## 7. 重新打包

在项目源码根目录下：

```bash
${PYTHON:-python3} scripts/package_linux_deb.py \
  --bundle-archive local/downloads/Muffin-v0.7.9-linux-x64.tar.gz \
  --qtbase-archive local/downloads/qtbase-6.11.1.7z \
  --qt-sdk local/qt-sdk \
  --output-dir packages/ibus3-rebuilt
```

脚本不安装软件，不修改全局环境或系统库，并拒绝覆盖既有同名安装包。
