# Muffin Markdown 独立 Debian 包

为了与 Debian/Cinnamon 的窗口管理器 `muffin` 共存，编辑器重新打包为 `muffin-md`。这是包名和安装位置的调整，不是重新编译编辑器；原应用内部名称仍为 Muffin，沿用原应用配置身份。

## 安装位置

- 包名：`muffin-md`，版本 `0.7.9-1+ibus4`。
- 命令：`/usr/bin/muffin-md`；Mermaid 工具：`/usr/bin/muffin-md-mmdc`。
- 私有运行库：`/usr/lib/muffin-md/`。
- 菜单入口：`/usr/share/applications/muffin-md.desktop`，显示名称 Muffin Markdown。
- 图标名：`muffin-md`；文档：`/usr/share/doc/muffin-md/`。

不声明替换或移除系统 `muffin`，也不占用其 `/usr/bin/muffin`、`muffin.desktop` 或 `/usr/share/doc/muffin/`。请勿继续安装旧的 `muffin_0.7.9-1+ibus4_amd64.deb`：其包名与系统窗口管理器相同。

在安装包所在目录执行：

```bash
sha256sum -c muffin-md_0.7.9-1+ibus4_amd64.deb.sha256
sudo apt install ./muffin-md_0.7.9-1+ibus4_amd64.deb
```

应用菜单选择 Muffin Markdown，或运行 `muffin-md 文件.md`。卸载编辑器使用 `sudo apt remove muffin-md`，不要卸载系统 `muffin`。

## 检查结果与限制

- 本机已安装 Cinnamon 窗口管理器 `muffin` 6.4.1-1；安装模拟显示新装 `muffin-md`、升级 0 个、删除 0 个。
- 对比本机 dpkg 已安装包文件清单，新包 88 个非目录路径无碰撞。
- 依赖和 ELF 符号扫描通过；包校验通过；desktop 文件验证无错误（仅 Utility 分类提示）。
- 新包中的 33 个私有运行文件与符号链接与原 ibus4 保存的哈希清单一致。
- 15 项打包测试通过；在实际 X11 下大图和小图各 9 个状态检查通过。
- 本轮输入法定位自动验收两次因测试窗口失焦而未完成，不能作为通过；原 ibus4 曾通过定位验收，新包运行文件与其一致，但本轮未重新验证真实 Rime 选词。
- 未执行系统安装、上游完整源码构建或全量 CTest。Wayland 和其他架构未验证。

## 重建

在源码根目录，使用已有的匹配 SDK 和两个固定哈希归档：

```bash
${PYTHON:-python3} scripts/package_linux_deb.py \
  --bundle-archive local/downloads/Muffin-v0.7.9-linux-x64.tar.gz \
  --qtbase-archive local/downloads/qtbase-6.11.1.7z \
  --qt-sdk local/qt-sdk \
  --output-dir packages/muffin-md-rebuilt
```

脚本拒绝覆盖已有的同名安装包。旧版历史文档中的 `muffin` 包名和安装指令仅用于记录，不能用于安装此新版。
