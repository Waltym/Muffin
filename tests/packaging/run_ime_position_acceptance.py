#!/usr/bin/env python3
"""Run a temporary X11 Muffin instance and verify automatic IBus position updates.

Only the diagnostic driver uses LD_PRELOAD. Production uses the private Qt input
plugin and needs no preload. No global fake keystrokes are sent by this test.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--qt-sdk', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--scale', type=float)
    parser.add_argument('--expect-failure', action='store_true', help='For the unfixed baseline only')
    args = parser.parse_args()
    bundle, sdk, output = args.bundle.resolve(), args.qt_sdk.resolve(), args.output_dir.resolve()
    if os.environ.get('XDG_SESSION_TYPE') != 'x11' or not os.environ.get('DISPLAY'):
        raise RuntimeError('A live X11 desktop session is required')
    output.mkdir(parents=True, exist_ok=False)
    driver = output / 'libime-position-acceptance.so'
    env = os.environ.copy()
    env.pop('LD_LIBRARY_PATH', None)
    flags = [f'-I{sdk / "include"}']
    flags += [f'-I{sdk / "include" / name}' for name in ('QtCore', 'QtGui', 'QtWidgets')]
    subprocess.run(['g++', '-shared', '-fPIC', '-std=c++20', '-O0', '-g', '-Wall', '-Wextra', '-Werror',
                    *flags, str(ROOT / 'tests/packaging/ImePositionAcceptance.cpp'), f'-L{bundle}',
                    f'-Wl,-rpath,{bundle}', '-l:libQt6Widgets.so.6', '-l:libQt6Gui.so.6',
                    '-l:libQt6Core.so.6', '-ldl', '-o', str(driver)], check=True, env=env)
    machine = Path('/etc/machine-id').read_text().strip()
    host, display = os.environ['DISPLAY'].split(':', 1)
    display = display.split('.', 1)[0]
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    busfile = config_home / 'ibus/bus' / f'{machine}-{host or "unix"}-{display}'
    if not busfile.is_file():
        raise FileNotFoundError(f'IBus address file not found: {busfile}')
    config = output / 'config/Muffin'
    config.mkdir(parents=True)
    (config / 'Muffin.conf').write_text('[update]\nautoCheck=false\n[view]\nsourceMode=false\n')
    document = output / 'position-test.md'
    document.write_text('\n\n'.join(
        'Paragraph %03d. Test cursor position near the line, not the bottom of the window.' % n
        for n in range(100)) + '\n')
    env.update(XDG_CONFIG_HOME=str(output / 'config'), XDG_DATA_HOME=str(output / 'data'),
               XDG_CACHE_HOME=str(output / 'cache'), IBUS_ADDRESS_FILE=str(busfile),
               QT_IM_MODULE='ibus', QT_QPA_PLATFORM='xcb', FONTCONFIG_FILE='/etc/fonts/fonts.conf',
               QT_LOGGING_RULES='qt.qpa.input.methods=true', LD_PRELOAD=str(driver))
    env.pop('QT_PLUGIN_PATH', None)
    if args.scale is not None:
        env['QT_SCALE_FACTOR'] = str(args.scale)
    with (output / 'acceptance.log').open('w') as log:
        process = subprocess.run([str(bundle / 'Muffin'), '--new-window', str(document)],
                                 env=env, stdout=log, stderr=log, timeout=25)
    log = (output / 'acceptance.log').read_text()
    summary = re.search(r'ACCEPT SUMMARY failures=\s*(\d+)', log)
    if not summary:
        raise RuntimeError(f'Test did not complete; inspect {output / "acceptance.log"}')
    cases = re.findall(r'ACCEPT ([\w-]+) ok=(true|false) updates=(\d+)', log)
    failures = int(summary.group(1))
    report = {'bundle': str(bundle), 'scale': args.scale, 'failures': failures,
              'exit_code': process.returncode, 'native_ibus_position_messages': log.count('microFocus QRect'),
              'cases': [{'name': n, 'passed': ok == 'true', 'updates': int(count)} for n, ok, count in cases]}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(cases) != 15:
        raise AssertionError(f'Expected all 15 acceptance cases, got {len(cases)}')
    if args.expect_failure:
        assert failures > 0 and process.returncode != 0, 'The baseline unexpectedly passed'
    else:
        assert failures == 0 and process.returncode == 0, 'Candidate-position acceptance failed'
        assert report['native_ibus_position_messages'] >= 14, 'IBus did not receive the expected position messages'


if __name__ == '__main__':
    main()
