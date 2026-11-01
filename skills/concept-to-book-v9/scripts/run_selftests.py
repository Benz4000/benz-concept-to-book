#!/usr/bin/env python3
"""Run the bundled synthetic tests in a fresh external directory. Python 3.12+."""
from __future__ import annotations
import argparse
import contextlib
import datetime
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def runtime_manifest():
    return {path.relative_to(ROOT).as_posix(): sha(path)
            for folder in ('scripts', 'selftests') for path in sorted((ROOT / folder).rglob('*'))
            if path.is_file() and path.suffix != '.pyc' and '__pycache__' not in path.parts}

class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'id': test.id(), 'status': 'pass'})
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({'id': test.id(), 'status': 'fail'})
    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({'id': test.id(), 'status': 'error'})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({'id': test.id(), 'status': 'skipped', 'reason': reason})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--run-name')
    parser.add_argument('--font', type=Path, help='Optional explicitly supplied TTF for print tests')
    parser.add_argument('--require-print', action='store_true', help='Fail rather than accept missing print dependencies/font')
    parser.add_argument('--renderer', type=Path, help='Optional existing pdftoppm executable for actual rendered-review tests')
    parser.add_argument('--require-renderer', action='store_true', help='Fail if the PDF renderer is unavailable')
    parser.add_argument('--pattern', default='test_*.py', help='A unittest discovery pattern; record partial coverage honestly')
    args = parser.parse_args()
    parent = args.output_root.resolve(strict=True)
    if not parent.is_dir() or parent == ROOT or ROOT in parent.parents:
        parser.error('output-root must be an existing directory outside the skill')
    name = args.run_name or datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name) or name.lower() in {'con','prn','aux','nul'} or re.fullmatch(r'(com|lpt)[1-9]', name.lower()):
        parser.error('run-name must be a safe single new directory name')
    destination = parent / name
    if destination.exists():
        parser.error('run directory exists; choose a new name')
    packages = {}
    for package in ('reportlab', 'pypdf', 'Pillow'):
        try: packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: packages[package] = None
    font = args.font.resolve(strict=True) if args.font else None
    if font is None and packages['reportlab']:
        import reportlab
        candidate = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
        if candidate.is_file(): font = candidate.resolve()
    if font is not None and (not font.is_file() or font.suffix.lower() != '.ttf'):
        parser.error('font must be an existing explicitly selected TTF file')
    if args.require_print and (not all(packages.values()) or font is None):
        parser.error('required print dependencies/font are unavailable; install the documented optional dependencies or supply a permitted TTF')
    renderer = args.renderer.resolve(strict=True) if args.renderer else None
    if renderer is None:
        found = os.environ.get('BOOK_TEST_PDFTOPPM') or shutil.which('pdftoppm')
        if found: renderer = Path(found).resolve(strict=True)
    if renderer and not renderer.is_file(): parser.error('renderer must be an existing executable file')
    if args.require_renderer and renderer is None: parser.error('required PDF renderer unavailable; select an existing pdftoppm executable')
    renderer_record = None
    if renderer:
        probe = subprocess.run([str(renderer), '-v'], capture_output=True, text=True, timeout=15)
        if probe.returncode != 0: parser.error('PDF renderer version probe failed')
        renderer_record = {'path': str(renderer), 'sha256': sha(renderer), 'version_output': (probe.stdout + probe.stderr).strip()}
    before = runtime_manifest()
    destination.mkdir()
    artifacts = destination / 'artifacts'
    artifacts.mkdir()
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['BOOK_TEST_ARTIFACT_ROOT'] = str(artifacts)
    if font: os.environ['BOOK_TEST_FONT'] = str(font)
    if renderer: os.environ['BOOK_TEST_PDFTOPPM'] = str(renderer)
    sys.path.insert(0, str(ROOT))
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        suite = unittest.TestLoader().discover(str(ROOT / 'selftests'), pattern=args.pattern, top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    unchanged = before == runtime_manifest()
    success = result.wasSuccessful() and result.testsRun > 0 and unchanged
    report = {'schema_version': 1, 'status': 'passed' if success else 'failed',
              'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'cases': result.records, 'pattern': args.pattern,
              'python': sys.version, 'platform': platform.platform(), 'packages': packages,
              'font': {'path': str(font), 'sha256': sha(font)} if font else None,
              'renderer': renderer_record,
              'runtime_sha256': before, 'runtime_unchanged': unchanged,
              'artifacts': str(artifacts), 'coverage': 'Synthetic local fixtures only; not a real book, human reading, visual acceptance, or platform certification.'}
    (destination / 'test-output.txt').write_text(log.getvalue(), encoding='utf-8')
    (destination / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('cases','runtime_sha256')}, indent=2))
    print('Report: ' + str(destination / 'results.json'))
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())
