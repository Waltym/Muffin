"""Standard-library regression tests for the local Debian repackager."""
import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_linux_deb', ROOT / 'scripts/package_linux_deb.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class RunpathTests(unittest.TestCase):
    def test_relocation_preserves_size_and_unrelated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plugin.so'
            old = b'ELF-prefix\0$ORIGIN/../../lib\0suffix'
            path.write_bytes(old)
            package.relocate_ibus_plugin(path)
            new = path.read_bytes()
            self.assertEqual(len(old), len(new))
            self.assertTrue(new.startswith(b'ELF-prefix\0$ORIGIN/..\0'))
            self.assertTrue(new.endswith(b'suffix'))

    def test_nested_native_plugin_runpath(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plugin.so'
            original = b'prefix\0$ORIGIN/../../lib\0suffix'
            path.write_bytes(original)
            package.relocate_ibus_plugin(path, b'$ORIGIN/../..\0')
            self.assertEqual(len(original), path.stat().st_size)
            self.assertIn(b'$ORIGIN/../..\0', path.read_bytes())

    def test_oversized_relocation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plugin.so'
            original = b'$ORIGIN/../../lib\0'
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                package.relocate_ibus_plugin(path, b'/unacceptably/long/path\0')
            self.assertEqual(original, path.read_bytes())

    def test_unknown_or_ambiguous_input_is_unchanged(self):
        for data in (b'unknown', b'$ORIGIN/../../lib\0' * 2):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'plugin.so'
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    package.relocate_ibus_plugin(path)
                self.assertEqual(data, path.read_bytes())


class HighlightPatchTests(unittest.TestCase):
    def original_css(self):
        css = (ROOT / 'resources/themes/document-base.css').read_bytes()
        for rule in (package.HIGHLIGHT_DEFAULT_RULE, package.IMAGE_FIT_DEFAULT_RULE):
            css = css.replace(rule, b'', 1)
        return css

    def test_changes_only_the_reserved_css_comment(self):
        css = self.original_css()
        prefix, suffix = b'ELF-code-and-data\0', b'\0untouched-symbols-and-code'
        old = prefix + css + suffix
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libMuffinUi.so'
            path.write_bytes(old)
            with patch.object(package, 'ORIGINAL_UI_SHA256', hashlib.sha256(old).hexdigest()):
                info = package.patch_highlight_default(path)
            new = path.read_bytes()
            start, size = info['css_comment_offset'], info['reserved_bytes']
            self.assertEqual(start, len(prefix))
            self.assertEqual(len(new), len(old))
            self.assertEqual(new[:start], old[:start])
            self.assertEqual(new[start+size:], old[start+size:])
            self.assertTrue(new[start:start+size].startswith(b'mark{background:#fff173}'))
            self.assertIn(b'img{max-width:100%;height:auto}', new[start:start+size])
            self.assertEqual(info['image_rule'], package.IMAGE_FIT_DEFAULT_RULE.decode().strip())
            self.assertNotEqual(info['original_sha256'], info['patched_sha256'])

    def test_missing_image_default_is_rejected(self):
        old = self.original_css()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libMuffinUi.so'
            path.write_bytes(old)
            with patch.object(package, 'ORIGINAL_UI_SHA256', hashlib.sha256(old).hexdigest()), \
                 patch.object(package, 'IMAGE_FIT_DEFAULT_RULE', b'img { invalid-test-rule: 1; }\n'):
                with self.assertRaises(ValueError):
                    package.patch_highlight_default(path)
            self.assertEqual(path.read_bytes(), old)

    def test_unknown_binary_is_not_modified(self):
        old = self.original_css()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libMuffinUi.so'
            path.write_bytes(old)
            with self.assertRaises(ValueError):
                package.patch_highlight_default(path)
            self.assertEqual(path.read_bytes(), old)

    def test_multiple_css_strings_are_rejected(self):
        old = self.original_css() * 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libMuffinUi.so'
            path.write_bytes(old)
            with patch.object(package, 'ORIGINAL_UI_SHA256', hashlib.sha256(old).hexdigest()):
                with self.assertRaises(ValueError):
                    package.patch_highlight_default(path)
            self.assertEqual(path.read_bytes(), old)

    def test_already_patched_binary_is_not_patched_again(self):
        old = self.original_css()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'libMuffinUi.so'
            path.write_bytes(old)
            with patch.object(package, 'ORIGINAL_UI_SHA256', hashlib.sha256(old).hexdigest()):
                package.patch_highlight_default(path)
                fixed = path.read_bytes()
                with self.assertRaises(ValueError):
                    package.patch_highlight_default(path)
            self.assertEqual(path.read_bytes(), fixed)


class LauncherTests(unittest.TestCase):
    def launch_environment(self, **updates):
        env = os.environ.copy()
        for key in ('QT_IM_MODULE', 'WAYLAND_DISPLAY', 'XMODIFIERS', 'FONTCONFIG_FILE'):
            env.pop(key, None)
        env.update(updates)
        script = package.LAUNCHER.replace(
            'exec /usr/lib/muffin-md/Muffin "$@"',
            'printf "%s|%s" "${QT_IM_MODULE:-}" "${FONTCONFIG_FILE:-}"')
        return subprocess.check_output(['/bin/sh', '-c', script], env=env, text=True)

    def test_x11_ibus_fallback(self):
        self.assertEqual(self.launch_environment(XMODIFIERS='@im=ibus'), 'ibus|/etc/fonts/fonts.conf')

    def test_explicit_input_method_and_fonts_are_preserved(self):
        self.assertEqual(self.launch_environment(XMODIFIERS='@im=ibus', QT_IM_MODULE='fcitx', FONTCONFIG_FILE='/custom/font.conf'), 'fcitx|/custom/font.conf')

    def test_wayland_does_not_force_ibus(self):
        self.assertEqual(self.launch_environment(XMODIFIERS='@im=ibus', WAYLAND_DISPLAY='wayland-0'), '|/etc/fonts/fonts.conf')

    def test_other_input_methods_are_not_changed(self):
        self.assertEqual(self.launch_environment(XMODIFIERS='@im=fcitx'), '|/etc/fonts/fonts.conf')


class PackageIdentityTests(unittest.TestCase):
    def test_launcher_and_desktop_use_independent_paths(self):
        self.assertEqual(package.PACKAGE, 'muffin-md')
        self.assertIn('exec /usr/lib/muffin-md/Muffin "$@"', package.LAUNCHER)
        self.assertIn('Exec=muffin-md %F\n', package.DESKTOP)
        self.assertIn('Icon=muffin-md\n', package.DESKTOP)


class SourcePackagingTests(unittest.TestCase):
    def test_all_qt_plugin_discovery_loops_include_input_contexts(self):
        for relative in ('CMakeLists.txt', 'cmake/MuffinDeploy.cmake'):
            text = (ROOT / relative).read_text()
            loops = [line for line in text.splitlines() if 'foreach(' in line and 'networkinformation' in line]
            self.assertTrue(loops)
            for line in loops:
                self.assertIn('platforminputcontexts', line)
        self.assertIn('self.options["qt/*"].with_dbus = True', (ROOT / 'conanfile.py').read_text())


if __name__ == '__main__':
    unittest.main()
