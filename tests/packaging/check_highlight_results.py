#!/usr/bin/env python3
"""Validate isolated MarkdownHighlightProbe logs and RGB PNG render results.

Requires Pillow in the selected test environment; does not install packages.
The images must come from temporary test documents, never user notes.
"""
import argparse
import json
from pathlib import Path
import re

from PIL import Image

YELLOW = (255, 241, 115)
NIGHT = (211, 212, 14)
GREEN = (0, 255, 0)


def color_counts(path):
    with Image.open(path) as image:
        rgb = image.convert('RGB')
        return {color: count for count, color in rgb.getcolors(rgb.width * rgb.height)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', required=True, type=Path)
    parser.add_argument('--baseline-night', type=Path)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    output = root / 'acceptance-summary.json'
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite {output}')
    cases = ('github', 'night', 'newsprint', 'pixyll', 'whitey', 'disabled',
             'live-toggle', 'custom-green', 'custom-transparent')
    summary = {}
    for name in cases:
        log = (root / name / 'probe.log').read_text()
        assert 'EXT_NO_' not in log, f'{name}: incomplete probe'
        assert 'EXT_STAGE cursor-away' in log, f'{name}: missing render stage'
        counts = color_counts(root / name / 'cursor-away.png')
        yellow, night, green = (counts.get(c, 0) for c in (YELLOW, NIGHT, GREEN))
        if name in ('github', 'newsprint', 'pixyll', 'whitey'):
            assert yellow > 500, f'{name}: missing default highlight pixels'
        elif name == 'night':
            assert night > 500 and yellow == 0, 'Night authored color was overridden'
        elif name == 'custom-green':
            assert green > 500 and yellow == 0, 'Custom authored color was overridden'
        else:
            assert yellow == 0, f'{name}: unwanted default highlight'
        if name == 'custom-transparent':
            assert 'EXT_MARK_STYLE QColor(ARGB 0, 0, 0, 0)' in log, 'Explicit transparent was not respected'
        if name not in ('disabled', 'live-toggle'):
            assert re.search(r'EXT_FORMAT .*baseline= -[\d.]', log), f'{name}: subscript regression'
            assert re.search(r'EXT_FORMAT .*baseline= [1-9][\d.]', log), f'{name}: superscript regression'
        summary[name] = {'default_yellow_pixels': yellow, 'night_color_pixels': night,
                         'custom_green_pixels': green, 'passed': True}
    live = root / 'live-toggle'
    log = (live / 'probe.log').read_text()
    assert 'EXT_PREFS_ENABLED 3' in log
    assert 'End of test H2O X2 typed' in log, 'Incremental input was not parsed'
    before = color_counts(live / 'initial.png').get(YELLOW, 0)
    after = color_counts(live / 'after-preferences.png').get(YELLOW, 0)
    typed = color_counts(live / 'incremental-input.png').get(YELLOW, 0)
    assert before == 0 and after > 500 and typed > after, 'Live setting or incremental highlight regression'
    summary['live-toggle']['stage_yellow_pixels'] = [before, after, typed]
    if args.baseline_night:
        with Image.open(args.baseline_night) as a, Image.open(root / 'night/cursor-away.png') as b:
            a, b = a.convert('RGB'), b.convert('RGB')
            assert a.size == b.size and a.tobytes() == b.tobytes(), 'Night pixels changed from the baseline'
        summary['night']['pixel_identical_to_ibus2'] = True
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    print('All 9 highlight rendering scenarios passed.')


if __name__ == '__main__':
    main()
