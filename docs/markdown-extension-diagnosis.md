# Muffin 0.7.9：上标、下标和高亮语法排查

> 后续：高亮缺省背景已在 ibus3 修复，详见 [高亮修复记录](markdown-highlight-fix-ibus3.md)。下文保留修复前的排查过程。

日期：2026-10-31。已安装包：`muffin 0.7.9-1+ibus2`。

## 结论

1. 用户配置中 `markdown/subscript`、`markdown/superscript`、`markdown/highlight` 均为 `true`，`view/sourceMode=false`。设置已保存，不是三个开关写入失败。
2. 在已安装的程序中，用标准写法 `H~2~O`、`X^2^` 实测，下标和上标有效；英文和中文内容都有效。目前未复现用户反馈的上下标无效果，需要用户提供实际输入的原始 Markdown 才能继续定位具体情形。
3. **高亮问题已复现并定位为主题/渲染默认值缺陷。** 默认 GitHub 主题下，`==文字==` 正常解析为高亮，标记也隐藏了，但没有底色。换用 Night 主题后底色正常。
4. 本次仅排查，没有修改系统安装程序、用户配置或用户现有笔记，也没有生成新版安装包。

## 复现与实际验证

### A. 对已安装解析库运行测试

使用匹配的 Qt 6.11.1 头文件，将项目已有测试链接到 `/usr/lib/muffin/libMuffinCore.so`，验证的是用户正在使用的解析实现，而非新构建的另一版解析库。

- `tests/document/HighlightParseTest.cpp`：6 项测试通过。
- `tests/document/SubscriptSuperscriptParseTest.cpp`：11 项测试通过，包含嵌套定界符、源坐标和固定语料检查。

仅为编译测试生成了 vendored cmark 的配置头文件；没有安装依赖或替换库。

测试程序及相关产物：`local/markdown-extension-tests/`。

### B. 对实际编辑器做运行时检查

在独立配置和临时文档中启动已安装的 `/usr/bin/muffin`，不使用用户会话或用户文档。诊断助手只在这些测试进程内加载，未修改生产启动器。

输入：

```markdown
Water: H~2~O; Area: X^2^; ==Highlight==

中文：H~二~O；X^上标^；==高亮==
```

开启三项扩展后，运行时显示文本变为：

```text
Water: H2O; Area: X2; Highlight
中文：H二O；X上标；高亮
```

这说明三种扩展都已进入解析与显示投影。下标文本格式记录到负基线偏移，上标记录到正基线偏移；实际 PNG 预览也确认上下标正常。

关闭扩展的对照组保留原始 `~`、`^`、`==` 标记，未出现上下标偏移。

### C. 设置窗口中的即时切换

测试从三项关闭开始，通过实际偏好设置窗口找到三个复选框并启用，然后关闭窗口：

- 日志记录三个复选框均被启用。
- 已打开的测试文档立即重新解析，上下标生效。
- 在临时文档中通过编辑器输入法提交事件追加 `H~2~O X^2^ ==typed==`，增量编辑路径也正确产生上下标。
- 高亮仍只有语法标记消失，没有底色。

这里的增量测试使用应用进程内的提交事件，验证的是编辑器的文本提交及增量解析链路，不应称作新一轮真实键盘/Rime 选词测试。

关键产物：

```text
local/markdown-extension-tests/live-toggle-with-caret/probe.log
local/markdown-extension-tests/live-toggle-with-caret/after-preferences.png
local/markdown-extension-tests/live-toggle-with-caret/incremental-input.png
```

### D. 主题对照

测试使用与用户相同的字号 20 和缩放 120%。

| 项目 | GitHub 主题 | Night 主题 |
|---|---|---|
| 下标、上标 | 正常 | 正常 |
| 高亮语法解析、隐藏标记 | 正常 | 正常 |
| `mark` 语义框背景色 | `QColor(Invalid)` | `#D3D40E` |
| 实际高亮底色 | 缺失 | 正常显示 |

两张预览均已实际读取检查：

```text
local/markdown-extension-tests/github-styles/cursor-away.png
local/markdown-extension-tests/night/cursor-away.png
```

## 高亮缺陷的代码链路

1. `src/app/MarkdownSettings.cpp` 正确读取三个扩展开关并传入解析选项。
2. `src/parser/CmarkGfmParser.cpp` 根据开关执行定界符后处理，生成 Highlight / Subscript / Superscript 节点。
3. `src/projection/InlineProjection.cpp` 将对应状态传播到文字片段，语法标记被折叠。
4. `src/render/InlineTextFormats.cpp` 起初给高亮片段设定背景，但计算出语义样式后执行 `format.clearBackground()`，将底色绘制交给 `mark` 语义框。
5. 默认 GitHub CSS 未定义 `mark` 背景，公共文档基础样式也没有补上有效默认值。运行时 `mark` 框背景无效，因此文字背景清除后，没有任何一层补画底色。
6. Night CSS 显式定义 `mark { background: #D3D40E; }`，语义框得到有效颜色，实际截图显示高亮正常。

需要区分：`RenderTheme::highlightBackgroundColor()` 本身仍有黄色令牌值，并非所有颜色数据都丢失；缺失的是接替实际绘制的语义 `mark` 样式。

## 建议处理

- 高亮：为语义 `mark` 提供合理的基础背景默认值，并允许主题显式样式覆盖；回归验证默认主题、Night 及自定义样式，避免简单强制覆盖所有主题颜色。
- 上下标：先核对用户实际测试内容、是否位于代码中、是否使用了全角符号或未闭合的标记；目前不能把尚未复现的现象归因于解析器失效。
- 临时验证高亮可切换 Night 主题，本次未代用户切换。

已另建独立示例：下载目录中的 `Muffin-Markdown扩展语法测试.md`。可直接打开核对；它不是用户原始笔记的修改版。
