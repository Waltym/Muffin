#!/usr/bin/env python3
"""Test large/small images in an isolated Muffin instance using generated bands.

Pillow is used only to create synthetic fixture PNGs. The Qt driver records
full-block image geometry and viewport colors without altering original files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    'github-wide': ('github', 'wide', '![TEST](../assets/wide.png)\n', None),
    'night-wide': ('night', 'wide', '![TEST](../assets/wide.png)\n', None),
    'newsprint-wide': ('newsprint', 'wide', '![TEST](../assets/wide.png)\n', None),
    'pixyll-wide': ('pixyll', 'wide', '![TEST](../assets/wide.png)\n', None),
    'whitey-wide': ('whitey', 'wide', '![TEST](../assets/wide.png)\n', None),
    'small': ('github', 'small', '![TEST](../assets/small.png)\n', None),
    'portrait': ('github', 'portrait', '![TEST](../assets/portrait.png)\n', None),
    'html-wide': ('github', 'wide', '<img src="../assets/wide.png">\n', None),
    'quote-wide': ('github', 'wide', '> ![TEST](../assets/wide.png)\n', None),
    'list-wide': ('github', 'wide', '- ![TEST](../assets/wide.png)\n', None),
    'custom-half': ('image-half', 'wide', '![TEST](../assets/wide.png)\n', 'img{max-width:50%;height:auto}'),
    'custom-width': ('image-width', 'wide', '![TEST](../assets/wide.png)\n', 'img{width:200px;height:auto}'),
}
SIZES = {'wide': (2400, 600), 'small': (160, 80), 'portrait': (900, 1800)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(rows, kind, html_source_mode=False):
    problems = []
    expected_stages = 10 if kind == 'portrait' else 9
    if len(rows) != expected_stages:
        problems.append(f'Expected {expected_stages} stages, got {len(rows)}')
    for row in rows:
        stage = row['stage']
        if stage == 'scrolled-bottom' and not (row['scroll_max'] > 0 and row['scroll_value'] == row['scroll_max']):
            problems.append('Portrait image did not scroll to its bottom')
        result = row['block_pixels']
        counts = result['counts']
        bounds = result['all']
        # Clicking an HTML block intentionally enters its source editor. It
        # must show the actual img source, not be treated as a clipped preview.
        if html_source_mode and stage == 'image-click' and max(counts) == 0 and '<img ' in row.get('literal', ''):
            continue
        if min(counts) < 20:
            problems.append(f'{stage}: missing image band(s): {counts}')
            continue
        actual = bounds[2] / bounds[3]
        expected = SIZES[kind][0] / SIZES[kind][1]
        if abs(actual - expected) > max(.03, 3 / bounds[3]):
            problems.append(f'{stage}: aspect ratio {actual:.5f}, expected {expected}')
        widths = [b[2] for b in result['bands']]
        if max(widths) - min(widths) > max(3, bounds[2] * .03):
            problems.append(f'{stage}: unbalanced bands indicate clipping: {widths}')
        if min(row['viewport_pixels']['counts']) < 20:
            problems.append(f'{stage}: right edge is not visible in the viewport')
        if kind == 'small':
            zoom = 2 if stage == 'zoom-200' else .8 if stage == 'zoom-80' else 1.2
            if abs(bounds[2] - 160 * zoom) > 2 or abs(bounds[3] - 80 * zoom) > 2:
                problems.append(f'{stage}: small image was enlarged beyond the selected editor zoom: {bounds}')
    return problems


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', required=True, type=Path)
    p.add_argument('--qt-sdk', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--case', action='append', choices=CASES, dest='cases')
    p.add_argument('--platform', choices=('xcb', 'offscreen'), default='xcb')
    p.add_argument('--expect-failure', action='store_true')
    args = p.parse_args()
    bundle, sdk, out = args.bundle.resolve(), args.qt_sdk.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop('LD_LIBRARY_PATH', None)
    driver = out / 'libimage-fit-probe.so'
    includes = [sdk / 'include', ROOT / 'src'] + [sdk / 'include' / n for n in ('QtCore', 'QtGui', 'QtWidgets')]
    subprocess.run(['g++', '-shared', '-fPIC', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                    *(f'-I{x}' for x in includes), str(ROOT / 'tests/packaging/ImageFitProbe.cpp'), f'-L{bundle}',
                    f'-Wl,-rpath,{bundle}', '-l:libMuffinUi.so', '-l:libMuffinCore.so', '-l:libQt6Widgets.so.6',
                    '-l:libQt6Gui.so.6', '-l:libQt6Core.so.6', '-ldl', '-o', str(driver)], check=True, env=env)
    assets = out / 'assets'
    assets.mkdir()
    for name, size in SIZES.items():
        image = Image.new('RGB', size, 'white')
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(('#e74c3c', '#2ecc71', '#3498db')):
            draw.rectangle((i*size[0]//3, 0, (i+1)*size[0]//3-1, size[1]-1), fill=color)
        image.save(assets / f'{name}.png')
    original_images = {x.name: sha(x) for x in assets.iterdir()}
    report = {}
    for name in args.cases or CASES:
        theme, kind, markdown, custom = CASES[name]
        directory = out / name
        conf = directory / 'config/Muffin'
        conf.mkdir(parents=True)
        (conf / 'Muffin.conf').write_text(f'[update]\nautoCheck=false\n[view]\nsourceMode=false\n'
                                         f'[appearance]\nthemeName={theme}\nfontSizePx=20\nzoomPercent=120\n')
        document = directory / 'image-test.md'
        document.write_text(markdown)
        document_hash = sha(document)
        if custom:
            themes = directory / 'data/Muffin/Muffin/themes'
            themes.mkdir(parents=True)
            # A valid Muffin theme must supply a readable document text color.
            (themes / f'{theme}.css').write_text('body{color:#333;background-color:#fff}\n' + custom)
        test_env = env.copy()
        test_env.update(XDG_CONFIG_HOME=str(directory/'config'), XDG_DATA_HOME=str(directory/'data'),
                        XDG_CACHE_HOME=str(directory/'cache'), QT_QPA_PLATFORM=args.platform,
                        FONTCONFIG_FILE='/etc/fonts/fonts.conf', LD_PRELOAD=str(driver),
                        MUFFIN_IMAGE_PROBE_OUT=str(directory))
        test_env.pop('QT_PLUGIN_PATH', None)
        if kind == 'portrait':
            test_env['MUFFIN_IMAGE_SCROLL_TEST'] = '1'
        with (directory / 'probe.log').open('w') as log:
            run = subprocess.run([str(bundle/'Muffin'), '--new-window', str(document)], env=test_env,
                                 stdout=log, stderr=log, timeout=35)
        rows = json.loads((directory/'geometry.json').read_text())
        problems = validate(rows, kind, html_source_mode=name == 'html-wide')
        if run.returncode:
            problems.append(f'Process failed: {run.returncode}')
        assert sha(document) == document_hash, 'Test document was unexpectedly changed'
        if name == 'custom-width':
            for row in rows:
                width = row['block_pixels']['all'][2]
                expected = 200 * (2 if row['stage']=='zoom-200' else .8 if row['stage']=='zoom-80' else 1.2)
                if abs(width-expected)>2: problems.append(f'Authored width not respected: {width}, expected {expected}')
        if name == 'custom-half':
            for row in rows:
                if abs(row['block_pixels']['all'][2]-row['block'][2]/2)>3:
                    problems.append('Authored 50% maximum width not respected')
        report[name] = {'passed': not problems, 'problems': problems, 'stage_count': len(rows),
                        'platform': args.platform, 'fixture': SIZES[kind]}
        print(name, json.dumps(report[name], ensure_ascii=False), flush=True)
    assert original_images == {x.name: sha(x) for x in assets.iterdir()}, 'Image originals were changed'
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    failures = [name for name, result in report.items() if not result['passed']]
    if args.expect_failure:
        assert failures, 'Unfixed baseline unexpectedly passed'
    else:
        assert not failures, f'Image fit regressions: {failures}'


if __name__ == '__main__':
    main()
