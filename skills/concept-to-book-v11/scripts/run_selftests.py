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
    parser.add_argument('--epubcheck-jar', type=Path, help='Existing optional EPUBCheck distribution jar; never downloaded by tests')
    parser.add_argument('--java', type=Path, help='Existing Java executable for optional EPUBCheck tests')
    parser.add_argument('--require-epubcheck', action='store_true', help='Require actual EPUBCheck integration coverage rather than a missing-tool skip')
    parser.add_argument('--pattern', default='test_*.py', help='A unittest discovery pattern; record partial coverage honestly')
    parser.add_argument('--reader-settings',type=Path,help='Existing explicit Node/playwright-core/Chromium settings JSON')
    parser.add_argument('--require-reader',action='store_true',help='Require actual browser integration rather than a missing-tool skip')
    parser.add_argument('--pdfinfo',type=Path,help='Existing optional Poppler pdfinfo executable')
    parser.add_argument('--require-pdfinfo',action='store_true',help='Require independent actual PDF parse coverage')
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
    epubcheck_record = None
    jar_value = args.epubcheck_jar or os.environ.get('V10_EPUBCHECK_JAR')
    java_value = args.java or os.environ.get('V10_JAVA') or shutil.which('java')
    required_epubcheck = args.require_epubcheck or os.environ.get('V10_REQUIRE_EPUBCHECK') == '1'
    if jar_value and java_value:
        jar, java = Path(jar_value).resolve(), Path(java_value).resolve()
        if not jar.is_file() or not java.is_file():
            parser.error('selected EPUBCheck jar/Java executable is missing')
        try:
            probe = subprocess.run([str(java), '-jar', str(jar), '--version'], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as error:
            parser.error('EPUBCheck capability probe failed: ' + str(error))
        version = (probe.stdout + probe.stderr).strip()
        if probe.returncode != 0 or 'EPUBCheck' not in version:
            parser.error('selected validator did not identify as EPUBCheck')
        epubcheck_record = {'jar': str(jar), 'jar_sha256': sha(jar), 'java': str(java), 'java_sha256': sha(java),
                           'version_output': version,
                           'library_sha256': {p.relative_to(jar.parent).as_posix(): sha(p) for p in sorted((jar.parent / 'lib').glob('*.jar'))}}
        os.environ['V10_EPUBCHECK_JAR'] = str(jar)
        os.environ['V10_JAVA'] = str(java)
    elif required_epubcheck:
        parser.error('required actual EPUBCheck unavailable; select an existing distribution jar and Java executable')
    if required_epubcheck: os.environ['V10_REQUIRE_EPUBCHECK'] = '1'
    reader_record=None
    reader_path=args.reader_settings or os.environ.get('V11_READER_SETTINGS')
    if reader_path:
        reader_path=Path(reader_path).resolve(strict=True)
        settings=json.loads(reader_path.read_text(encoding='utf-8-sig'))
        if not all(settings.get(k) and Path(settings[k]).is_file() for k in ('node','playwright_module','browser')):parser.error('Selected reader tool path missing')
        probe=subprocess.run([settings['node'],'--version'],capture_output=True,text=True,timeout=15)
        if probe.returncode:parser.error('Node capability probe failed')
        reader_record={'settings':str(reader_path),'settings_sha256':sha(reader_path),'node_version':probe.stdout.strip(),'tools':{k:{'path':settings[k],'sha256':sha(Path(settings[k]))} for k in ('node','playwright_module','browser')}}
        os.environ['V11_READER_SETTINGS']=str(reader_path)
    elif args.require_reader:parser.error('Actual reader settings required')
    if args.require_reader:os.environ['V11_REQUIRE_READER']='1'
    pdfinfo=args.pdfinfo or os.environ.get('V11_PDFINFO') or shutil.which('pdfinfo')
    pdfinfo_record=None
    if pdfinfo:
        pdfinfo=Path(pdfinfo).resolve(strict=True);probe=subprocess.run([str(pdfinfo),'-v'],capture_output=True,text=True,timeout=15)
        if probe.returncode:parser.error('pdfinfo capability probe failed')
        pdfinfo_record={'path':str(pdfinfo),'sha256':sha(pdfinfo),'version':(probe.stdout+probe.stderr).strip()};os.environ['V11_PDFINFO']=str(pdfinfo)
    elif args.require_pdfinfo:parser.error('Actual pdfinfo required')
    before = runtime_manifest()
    destination.mkdir()
    artifacts = destination / 'artifacts'
    artifacts.mkdir()
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['BOOK_TEST_ARTIFACT_ROOT'] = str(artifacts)
    os.environ['V11_ARTIFACT_ROOT'] = str(artifacts)
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
              'epubcheck': epubcheck_record,
              'reader':reader_record,'pdfinfo':pdfinfo_record,
              'runtime_sha256': before, 'runtime_unchanged': unchanged,
              'artifacts': str(artifacts), 'coverage': 'Synthetic local fixtures only; not a real book, human reading, visual acceptance, or platform certification.'}
    (destination / 'test-output.txt').write_text(log.getvalue(), encoding='utf-8')
    (destination / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('cases','runtime_sha256')}, indent=2))
    print('Report: ' + str(destination / 'results.json'))
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())
