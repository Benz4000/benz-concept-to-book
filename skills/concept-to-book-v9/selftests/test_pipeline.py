"""Actual manuscript -> reading/PDF files -> audits -> impact -> review packet."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
def tree(root): return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file()}
def png():
    width, height = 160, 80
    rows = b''.join(b'\x00' + bytes([22, 48, 61] if y % 16 < 8 else [220, 175, 70]) * width for y in range(height))
    def chunk(kind, data): return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width,height,8,2,0,0,0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')

class FullPipeline(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get('BOOK_TEST_ARTIFACT_ROOT')
        self.temp = None
        if retained:
            self.work = Path(tempfile.mkdtemp(prefix='pipeline-', dir=retained))
        else:
            self.temp = tempfile.TemporaryDirectory(prefix='book-pipeline-')
            self.work = Path(self.temp.name) / 'work'
            self.work.mkdir()
        self.source = self.work / 'source'; self.source.mkdir()
        self.outputs = self.work / 'outputs'; self.outputs.mkdir()
        self.logs = self.work / 'logs'; self.logs.mkdir()
        self.counter = 0
        self.original = '# Before the Crossing\n\nThis miniature is a synthetic production test.\n\n# The Lantern\n\nMara carried the lantern across the rain-dark causeway. The keeper followed, counting each steady footstep.\n\nCaf\u00e9 lights waited on the farther shore.\n\n# Afterword\n\nNo historical claims or real locations are represented.\n'
        (self.source / 'book.md').write_text(self.original, encoding='utf-8')
        self.meta = {'title':'The Lantern at the Crossing','author':'Fixture Author','identifier':'urn:test:lantern-v8','language':'en','modified':'2026-10-31T00:00:00Z'}
        write_json(self.source / 'metadata.json', self.meta)

    def tearDown(self):
        if self.temp: self.temp.cleanup()

    def cli(self, name, args, success=True):
        self.counter += 1
        command = [sys.executable, '-B', str(ROOT/'scripts'/name), *map(str,args)]
        proc = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'})
        write_json(self.logs / f'{self.counter:02d}-{Path(name).stem}.json', {'command':command,'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
        if success: self.assertEqual(proc.returncode,0,proc.stdout+'\n'+proc.stderr)
        else: self.assertNotEqual(proc.returncode,0,proc.stdout)
        return proc

    def import_book(self, name):
        self.cli('import_manuscript.py',['--input-root',self.source,'--input','book.md','--metadata','metadata.json','--output-root',self.outputs,'--output-dir',name])
        return self.outputs/name

    def add_assets(self, imported):
        config = json.loads((imported/'edition.json').read_text(encoding='utf-8'))
        self.assertEqual(len(config['sections']),3)
        config['sections'][0]['part']='front';config['sections'][-1]['part']='back'
        (imported/'art').mkdir()
        (imported/'art/route.png').write_bytes(png())
        config['assets']=[{'id':'route','path':'art/route.png','role':'map','alt':'Synthetic amber and navy route test pattern.'}]
        middle=imported/config['sections'][1]['source']
        blocks=json.loads(middle.read_text(encoding='utf-8'))
        blocks['blocks'].append({'type':'image','asset_id':'route','caption':'Synthetic test image; not finished book artwork.'})
        write_json(middle,blocks);write_json(imported/'edition.json',config)
        return config

    def test_import_build_audit_change_and_review(self):
        original_hashes=tree(self.source)
        first=self.import_book('import-one'); config=self.add_assets(first)
        self.assertEqual(original_hashes,tree(self.source))
        self.cli('build_reading_edition.py',['--input-root',first,'--config','edition.json','--output-root',self.outputs,'--output-dir','reading-one'])
        reading=self.outputs/'reading-one'; old_release=tree(reading)
        audit=self.cli('audit_exports.py',['--input-root',first,'--config','edition.json','--release-root',reading])
        self.assertTrue(json.loads(audit.stdout)['ok'])
        graph={'schema_version':1,'artifacts':[
            {'id':'manuscript','path':'source/book.md'},
            {'id':'reading','path':'outputs/reading-one/html/index.html','depends_on':['manuscript']},
            {'id':'unrelated','path':'source/metadata.json'}],
            'checks':[{'id':'reading-review','inputs':['reading'],'status':'passed','reviewed_sha256':{'reading':sha(reading/'html/index.html')}},
                      {'id':'other-review','inputs':['unrelated'],'status':'passed','reviewed_sha256':{'unrelated':sha(self.source/'metadata.json')}}]}
        write_json(self.work/'graph.json',graph)
        baseline=self.cli('plan_changes.py',['--root',self.work,'--graph','graph.json'])
        (self.work/'baseline.json').write_text(baseline.stdout,encoding='utf-8')
        (self.source/'previous.md').write_text(self.original,encoding='utf-8')
        (self.source/'book.md').write_text(self.original.replace('counting each steady footstep','holding the ledger above the rising water'),encoding='utf-8')
        changed=self.cli('plan_changes.py',['--root',self.work,'--graph','graph.json','--baseline','baseline.json'])
        report=json.loads(changed.stdout)
        impacts={item['artifact_id']:item for item in report['changes']}
        self.assertIn('manuscript',impacts);self.assertTrue(impacts['reading']['transitive']);self.assertNotIn('unrelated',impacts)
        checks={item['check_id']:item for item in report['checks']}
        self.assertTrue(checks['reading-review']['reconsider'])
        self.assertFalse(checks.get('other-review',{}).get('reconsider',False))
        second=self.import_book('import-two');self.add_assets(second)
        self.cli('build_reading_edition.py',['--input-root',second,'--config','edition.json','--output-root',self.outputs,'--output-dir','reading-two'])
        self.cli('audit_exports.py',['--input-root',second,'--config','edition.json','--release-root',self.outputs/'reading-two'])
        self.cli('audit_exports.py',['--input-root',second,'--config','edition.json','--release-root',reading],success=False)
        self.assertEqual(old_release,tree(reading))
        packet={'schema_version':1,'title':'Synthetic revision review','criteria':['Check the changed action in context.','Preserve the ending.'],
                'items':[{'id':'scene','label':'Changed manuscript','current':'source/book.md','previous':'source/previous.md','context':['source/metadata.json']} ]}
        write_json(self.work/'packet.json',packet)
        packet_parent=self.work.parent/'review-packets';packet_parent.mkdir(exist_ok=True)
        self.cli('make_review_packet.py',['--root',self.work,'--manifest','packet.json','--output-root',packet_parent,'--output-dir',self.work.name])
        packet_root=packet_parent/self.work.name
        provenance=json.loads((packet_root/'provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['review_scope']['status'],'pending')
        html=(packet_root/'index.html').read_text(encoding='utf-8')
        self.assertIn('holding the ledger',html);self.assertIn('counting each steady footstep',html)

    @unittest.skipUnless(importlib.util.find_spec('reportlab') and importlib.util.find_spec('pypdf') and importlib.util.find_spec('PIL'),'Optional print dependencies unavailable')
    def test_import_to_actual_pdf_and_audit(self):
        import reportlab
        default_font=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
        font=Path(os.environ.get('BOOK_TEST_FONT',str(default_font)))
        if not font.is_file():self.skipTest('Supplied test font unavailable')
        imported=self.import_book('print-source');self.add_assets(imported)
        (imported/'fonts').mkdir();shutil.copyfile(font,imported/'fonts/fixture.ttf')
        settings=json.loads((ROOT/'assets/templates/print-settings.json').read_text(encoding='utf-8'))
        settings['font']={'path':'fonts/fixture.ttf','embedding_authorized':True}
        write_json(imported/'print-settings.json',settings)
        before=tree(imported)
        args=['--input-root',imported,'--config','edition.json','--settings','print-settings.json','--output-root',self.outputs]
        self.cli('build_print_edition.py',args+['--output-dir','print-one'])
        self.cli('build_print_edition.py',args+['--output-dir','print-two'])
        self.assertEqual(before,tree(imported))
        self.assertEqual(tree(self.outputs/'print-one'),tree(self.outputs/'print-two'))
        audit=self.cli('audit_exports.py',['--input-root',imported,'--config','edition.json','--settings','print-settings.json','--release-root',self.outputs/'print-one'])
        self.assertTrue(json.loads(audit.stdout)['ok'])

if __name__ == '__main__': unittest.main()
