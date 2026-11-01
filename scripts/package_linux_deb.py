#!/usr/bin/env python3
"""Repackage Muffin 0.7.9 with Qt IBus, caret, highlight and responsive image fixes.

Requires existing 7z/dpkg tools, g++, and the pinned Qt 6.11.1 SDK headers/moc.
Does not install anything, change profiles, or rebuild the editor itself.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[1]
VERSION = "0.7.9-1+ibus4"
PACKAGE = "muffin-md"
ORIGINAL_UI_SHA256 = "a1c3fe544698f7a626f90c0eed7b81c34e1e506d1952ce3275e9b940165c3776"
HIGHLIGHT_DEFAULT_RULE = b"mark { background-color: #fff173; }\n"
IMAGE_FIT_DEFAULT_RULE = b"img { max-width: 100%; height: auto; }\n"
HASHES = {
    "muffin": "e53f83505509d1c407dcdbee381f45662e1121fe995d2f3bee846fd50f624214",
    "qtbase": "1d6d82d765987d657d0df136fb347e98d6e29e99ef8d1cb433abf9f15c86ab6f",
}
SOURCES = {
    "muffin": "https://github.com/jstzwj/Muffin/releases/download/v0.7.9/Muffin-v0.7.9-linux-x64.tar.gz",
    "qtbase": "https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/qt6_6111/qt6_6111/qt.qt6.6111.linux_gcc_64/6.11.1-0-202605090529qtbase-Linux-RHEL_9_6-GCC-Linux-RHEL_9_6-X86_64.7z",
}
LAUNCHER = '''#!/bin/sh
# Only affect this application; preserve an explicitly selected input method.
if [ -z "${QT_IM_MODULE:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    case "${XMODIFIERS:-}" in
        *@im=ibus*) export QT_IM_MODULE=ibus ;;
    esac
fi
# The upstream build embeds a build-machine fontconfig default path.
if [ -z "${FONTCONFIG_FILE:-}" ] && [ -r /etc/fonts/fonts.conf ]; then
    export FONTCONFIG_FILE=/etc/fonts/fonts.conf
fi
exec /usr/lib/muffin-md/Muffin "$@"
'''
DESKTOP = '''[Desktop Entry]
Type=Application
Name=Muffin Markdown
GenericName=Markdown Editor
GenericName[zh_CN]=Markdown 编辑器
Comment=Native Markdown editor with IBus input support
Comment[zh_CN]=支持 IBus 中文输入的原生 Markdown 编辑器
Exec=muffin-md %F
Icon=muffin-md
Terminal=false
Categories=Office;TextEditor;
MimeType=text/markdown;text/x-markdown;
StartupWMClass=Muffin
Keywords=Markdown;Editor;Notes;
'''


def put(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_elf(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as stream:
        return stream.read(4) == b"\x7fELF"


def relocate_ibus_plugin(path, replacement=b"$ORIGIN/..\0"):
    # Equivalent to chrpath: shorten the single existing DT_RUNPATH string in
    # place without moving ELF sections. The hash-pinned SDK has this exact
    # string once. Leave the original SDK archive and extracted binary intact.
    original = b"$ORIGIN/../../lib\0"
    if len(replacement) > len(original) or not replacement.endswith(b"\0"):
        raise ValueError("Replacement RUNPATH must fit the original string")
    data = path.read_bytes()
    if data.count(original) != 1:
        raise ValueError("Unexpected IBus plugin RUNPATH; refusing binary patch")
    path.write_bytes(data.replace(original, replacement.ljust(len(original), b"\0")))


def patch_highlight_default(path):
    """Patch only default CSS data in a hash-pinned COPY of the upstream UI.

    Historical name retained: this now includes responsive images as well as
    mark. The 77-byte comment holds the two compact rules plus whitespace.
    File/string size, code and ELF offsets stay unchanged. Full-source builds
    use document-base.css directly instead.
    """
    original_hash = digest(path)
    if original_hash != ORIGINAL_UI_SHA256:
        raise ValueError("Unexpected MuffinUi SHA256; refusing highlight patch")
    source_css = (REPO / "resources/themes/document-base.css").read_bytes()
    defaults = (HIGHLIGHT_DEFAULT_RULE, IMAGE_FIT_DEFAULT_RULE)
    old_css = source_css
    for rule in defaults:
        if source_css.count(rule) != 1:
            raise ValueError("Expected exactly one of each default rule in source CSS")
        old_css = old_css.replace(rule, b"", 1)
    comment = old_css.splitlines(keepends=True)[0]
    if not comment.startswith(b"/* Muffin's document host contract.") or not comment.endswith(b"*/\n"):
        raise ValueError("Unexpected embedded CSS comment")
    # Compact ONLY these two fixed, validated rules, never arbitrary theme CSS.
    replacement = b"".join(rule.translate(None, b" \t\r\n").replace(b"background-color:", b"background:")
                           .replace(b";}", b"}") for rule in defaults)
    embedded_rules = replacement.decode()
    if len(replacement) + 1 > len(comment):
        raise ValueError("Default rules do not fit the reserved comment")
    replacement = replacement.ljust(len(comment) - 1, b" ") + b"\n"
    data = path.read_bytes()
    if data.count(old_css) != 1:
        raise ValueError("Expected exactly one complete upstream base CSS string")
    offset = data.index(old_css)
    patched = data[:offset] + replacement + data[offset + len(comment):]
    if len(patched) != len(data):
        raise AssertionError("CSS patch unexpectedly changed ELF size")
    path.write_bytes(patched)
    return {"original_sha256": original_hash, "patched_sha256": digest(path),
            "css_comment_offset": offset, "reserved_bytes": len(comment),
            "file_size": len(patched), "rule": HIGHLIGHT_DEFAULT_RULE.decode().strip(),
            "image_rule": IMAGE_FIT_DEFAULT_RULE.decode().strip(), "embedded_rules": embedded_rules}


def build_position_adapter(sdk, runtime, build, output, env):
    sdk = sdk.resolve()
    moc = sdk / "libexec/moc"
    if not moc.is_file() or not (sdk / "include/QtCore/6.11.1").is_dir():
        raise ValueError("The exact Qt 6.11.1 SDK headers and moc are required")
    source = REPO / "src/platform/ibus/MuffinIBusPlugin.cpp"
    build.mkdir(parents=True)
    includes = [build, sdk / "include"]
    includes += [sdk / "include" / name for name in ("QtCore", "QtGui", "QtWidgets")]
    for name in ("QtCore", "QtGui"):
        includes += [sdk / "include" / name / "6.11.1", sdk / "include" / name / "6.11.1" / name]
    flags = [f"-I{path}" for path in includes]
    moc_env = env.copy()
    moc_env["LD_LIBRARY_PATH"] = str(runtime)
    version = subprocess.check_output([str(moc), "-v"], env=moc_env, text=True, stderr=subprocess.STDOUT)
    if "moc 6.11.1" not in version:
        raise ValueError(f"Unexpected moc version: {version}")
    subprocess.run([str(moc), *flags, str(source), "-o", str(build / "MuffinIBusPlugin.moc")], check=True, env=moc_env)
    subprocess.run(["g++", "-shared", "-fPIC", "-fvisibility=hidden", "-std=c++20", "-O2",
                    "-Wall", "-Wextra", "-Werror", *flags, str(source), f"-L{runtime}",
                    "-l:libQt6Widgets.so.6", "-l:libQt6Gui.so.6", "-l:libQt6Core.so.6",
                    "-Wl,-z,defs", "-Wl,-rpath,$ORIGIN/..", "-o", str(output)], check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-archive", required=True, type=Path)
    parser.add_argument("--qtbase-archive", required=True, type=Path)
    parser.add_argument("--qt-sdk", required=True, type=Path, help="Extracted Qt 6.11.1 include/ and libexec/moc")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    inputs = {"muffin": args.bundle_archive.resolve(), "qtbase": args.qtbase_archive.resolve()}
    for kind, path in inputs.items():
        if digest(path) != HASHES[kind]:
            raise ValueError(f"Unexpected {kind} archive SHA256: {path}")
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    if arch != "amd64":
        raise ValueError("The pinned upstream archive is amd64 only")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve() / f"{PACKAGE}_{VERSION}_amd64.deb"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env["LC_ALL"] = "C"
    with tempfile.TemporaryDirectory(prefix="muffin-deb-", dir=args.output_dir) as temporary:
        work = Path(temporary).resolve()
        root = work / "package"
        app = root / "usr/lib/muffin-md"
        app.mkdir(parents=True)
        with tarfile.open(inputs["muffin"], "r:gz") as archive:
            archive.extractall(app, filter="data")
        highlight_patch = patch_highlight_default(app / "libMuffinUi.so")
        sdk = work / "qt-sdk"
        subprocess.run(["7z", "x", str(inputs["qtbase"]), f"-o{sdk}",
                        "lib/libQt6DBus.so.6.11.1",
                        "plugins/platforminputcontexts/libibusplatforminputcontextplugin.so"], check=True, env=env)
        shutil.copy2(sdk / "lib/libQt6DBus.so.6.11.1", app)
        (app / "libQt6DBus.so.6").symlink_to("libQt6DBus.so.6.11.1")
        plugin = app / "platforminputcontexts/libibusplatforminputcontextplugin.so"
        native = plugin.parent / "upstream" / plugin.name
        native.parent.mkdir(parents=True)
        shutil.copy2(sdk / "plugins/platforminputcontexts" / plugin.name, native)
        relocate_ibus_plugin(native, b"$ORIGIN/../..\0")
        build_position_adapter(args.qt_sdk, app, work / "adapter-build", plugin, env)
        put(root / "usr/bin/muffin-md", LAUNCHER, 0o755)
        put(root / "usr/bin/muffin-md-mmdc", '#!/bin/sh\nexec /usr/lib/muffin-md/muffin-mmdc "$@"\n', 0o755)
        put(root / "usr/share/applications/muffin-md.desktop", DESKTOP)
        for size in (16, 32, 48, 64, 128, 256, 512):
            icon = REPO / f"resources/app-icons/muffin-{size}.png"
            if not icon.exists():
                icon = REPO / f"resources/app-icons/{size}.png"
            if icon.exists():
                dest = root / f"usr/share/icons/hicolor/{size}x{size}/apps/muffin-md.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(icon, dest)
        scalable = root / "usr/share/icons/hicolor/scalable/apps/muffin-md.svg"
        scalable.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "logo.svg", scalable)
        doc = root / "usr/share/doc/muffin-md"
        doc.mkdir(parents=True)
        shutil.copy2(REPO / "LICENSE", doc / "copyright")
        for license_name in ("LGPL-3", "GPL-3"):
            shutil.copy2(Path("/usr/share/common-licenses") / license_name, doc / license_name)
        for path in (REPO / "third_party").rglob("*"):
            if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING")):
                dest = doc / "third-party-licenses" / path.relative_to(REPO / "third_party")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        put(doc / "README.ibus.zh-CN", """Muffin 0.7.9 / Debian amd64 本地输入法修复包

使用官方 0.7.9 编辑器及 Qt 6.11.1 IBus/D-Bus 组件，不重新编译编辑器。
保留 mark 默认背景 #fff173；ibus4 增加 img 的 max-width:100% 和 height:auto，
大图按正文宽度等比缩小，小图不强制放大。主题和行内的显式样式继续优先。
仅在经过 SHA256 校验的打包副本中等长替换基础 CSS 的开头注释，
不改变 ELF 文件大小、字符串长度或代码；修改偏移及新旧哈希见 build-inputs.json。
额外编译 Muffin 专用 IBus 位置适配插件：仍由原版 Qt IBus 处理输入，
在光标、预编辑、滚动、窗口尺寸/位置变化后合并并补发光标定位通知。
无轮询，不截获按键、不修改文本或坐标缩放规则；仅对 Muffin 两种编辑器生效。
原版插件位于 platforminputcontexts/upstream/，RUNPATH 为 $ORIGIN/../..；
适配插件 RUNPATH 为 $ORIGIN/..。Qt 动态库保持私有，不替换系统 Qt，
不修改 IBus/Rime 配置，也不设置系统或应用启动器的 LD_PRELOAD。
启动器仅在未指定 QT_IM_MODULE 且 XMODIFIERS 指定 ibus 的 X11 会话中
为本进程设置 QT_IM_MODULE=ibus；为本进程补齐默认 fontconfig 配置路径。

安装/升级：sudo apt install ./muffin-md_0.7.9-1+ibus4_amd64.deb
启动：应用菜单中的 Muffin Markdown，或 muffin-md 文件.md
卸载：sudo apt remove muffin-md（用户笔记不在本包内）
包名、启动器和安装目录与 Cinnamon 窗口管理器 muffin 分离。
适用：已在 Debian 13 amd64 / GNOME X11 上验证；其他发行版、Wayland 未验证。
请勿向此私有运行库目录复制其他版本 Qt 的输入法插件。

上游：https://github.com/jstzwj/Muffin/tree/v0.7.9 （MIT）
Qt 源码：https://download.qt.io/archive/qt/6.11/6.11.1/submodules/qtbase-everywhere-src-6.11.1.tar.xz
Qt 动态库及插件采用 LGPLv3，可使用兼容 ABI 的自行构建版本替换。
各第三方组件遵循各自许可证；适配源码及打包脚本随包提供于 ibus-position-source/。
""")
        position_sources = REPO / "src/platform/ibus"
        for path in position_sources.iterdir():
            if path.is_file():
                dest = doc / "ibus-position-source" / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        shutil.copy2(Path(__file__), doc / "ibus-position-source/package_linux_deb.py")
        shutil.copy2(REPO / "resources/themes/document-base.css", doc / "document-base.css")
        put(doc / "build-inputs.json", json.dumps({
            "package_name": PACKAGE, "package_version": VERSION, "application_version": "0.7.9", "qt_version": "6.11.1",
            "strategy": "upstream-binary-repack+compiled-private-ibus-position-adapter+checked-base-css-data-patch; editor not rebuilt",
            "highlight_base_css_patch": highlight_patch,
            "document_base_css_sha256": digest(REPO / "resources/themes/document-base.css"),
            "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
            "position_source_sha256": {p.name: digest(p) for p in sorted(position_sources.iterdir()) if p.is_file()},
            "position_adapter_sha256": digest(plugin),
            "inputs": {k: {"url": SOURCES[k], "sha256": HASHES[k]} for k in inputs},
            "plugin_runpath": "$ORIGIN/..", "native_ibus_plugin_runpath": "$ORIGIN/../..",
        }, indent=2) + "\n")
        # Mark the private bundled Qt libraries locally so dpkg-shlibdeps does
        # not incorrectly require Debian's ABI-incompatible system Qt packages.
        put(work / "debian/control", f"Source: {PACKAGE}\nSection: editors\nPriority: optional\nMaintainer: Local Build <local@localhost>\nStandards-Version: 4.7.0\n\nPackage: {PACKAGE}\nArchitecture: amd64\nDescription: Muffin Markdown editor\n")
        qt_names = ("Core", "Gui", "Widgets", "Network", "PrintSupport", "Svg", "XcbQpa", "DBus")
        put(work / "debian/shlibs.local", "".join(f"libQt6{name} 6 {PACKAGE}\n" for name in qt_names))
        (root / "DEBIAN").mkdir()
        binaries = sorted(p for p in app.rglob("*") if is_elf(p))
        scan = subprocess.run(["dpkg-shlibdeps", "--ignore-missing-info", "-O", f"-x{PACKAGE}",
                               f"-l{app}", *(f"-e{p}" for p in binaries)],
                              cwd=work, env=env, text=True, capture_output=True, check=True)
        dependencies = scan.stdout.strip().removeprefix("shlibs:Depends=")
        if "libqt6" in dependencies or "qt6-base-private-abi" in dependencies:
            raise ValueError(f"Bundled Qt incorrectly resolved to system Qt: {dependencies}")
        put(args.output_dir / "dependency-scan.log", scan.stdout + scan.stderr)
        for binary in binaries:
            check = subprocess.run(["ldd", "-r", str(binary)], text=True, capture_output=True, env=env, check=True)
            if "not found" in check.stdout or "undefined symbol:" in check.stdout or "undefined symbol:" in check.stderr:
                raise ValueError(f"Unresolved runtime ABI for {binary}: {check.stdout}{check.stderr}")
        installed_kib = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()) // 1024 + 1
        put(root / "DEBIAN/control", f"""Package: {PACKAGE}
Version: {VERSION}
Section: editors
Priority: optional
Architecture: amd64
Maintainer: Local Build <local@localhost>
Installed-Size: {installed_kib}
Depends: {dependencies}, fontconfig-config
Recommends: ibus, fonts-noto-cjk
Homepage: https://github.com/jstzwj/Muffin
Description: Native WYSIWYG Markdown editor with IBus input support
 Upstream Muffin 0.7.9 with matching Qt 6.11.1 IBus, D-Bus runtime,
 a private caret-position adapter, default mark background and responsive images.
 No global input-method changes.
""")
        # dpkg-deb computes ownership as root without requiring sudo/fakeroot.
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "-z6", "--build", str(root), str(output)], check=True, env=env)
    checksum = digest(output)
    put(output.with_suffix(".deb.sha256"), f"{checksum}  {output.name}\n")
    print(f"Built: {output}\nSHA256: {checksum}")


if __name__ == "__main__":
    main()
