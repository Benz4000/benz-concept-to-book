"""Actual CLI regressions for explicit execution, recovery and source evidence."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

def digest(data):
    return hashlib.sha256(data).hexdigest()

class RunnerSources(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.inputs=self.root/'selected'
        self.out=self.root/'out'
        self.inputs.mkdir(); self.out.mkdir()
        (self.inputs/'book.md').write_text('# One\n\nFirst paragraph.\n',encoding='utf-8')
        self.write('metadata.json',{'title':'Proof','author':'Author','identifier':'urn:test:proof','language':'en','modified':'2026-10-31T00:00:00Z'})
        self.cfg={'schema_version':1,'input_root':str(self.inputs),'selected_inputs':['book.md','metadata.json'],'import':{'manuscript':'book.md','metadata':'metadata.json'},'edition':{'edition_id':'proof','formats':['html','epub'],'assets':[],'sections':[{'id':'section-0001','part':'body','kind':'chapter'}]}}
        self.manifest=self.root/'project.json'
        self.save_manifest()
    def write(self,name,data):
        (self.inputs/name).write_text(json.dumps(data),encoding='utf-8')
    def save_manifest(self):
        self.manifest.write_text(json.dumps(self.cfg),encoding='utf-8')
    def cli(self,script,*args,ok=True):
        p=subprocess.run([sys.executable,'-B',str(SCRIPTS/script),*map(str,args)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode==0,ok,p.stdout+'\n'+p.stderr)
        return json.loads(p.stdout)
    def run_cli(self,*extra,ok=True):
        return self.cli('run_project.py','--manifest',self.manifest,'--output-root',self.out,*extra,ok=ok)
    def execute(self,*extra):
        return self.run_cli('--execute','--stages','import,prepare,digital,audit-digital',*extra)
    def test_plan_conflicts_escape_and_execute_scope(self):
        before=list(self.out.iterdir())
        plan=self.run_cli('--stages','digital')
        self.assertTrue(plan['conflicts'])
        self.assertEqual(before,list(self.out.iterdir()))
        self.run_cli('--execute','--stages','digital',ok=False)
        self.cfg['edition']['sections'][0]['part']='wrong'; self.save_manifest()
        self.run_cli(ok=False)
        self.cfg['edition']['sections'][0]['part']='body'
        self.cfg['selected_inputs'].append('../escape'); self.save_manifest()
        self.run_cli(ok=False)
    def test_resume_interruption_tamper_and_changes(self):
        first=self.execute(); prior=Path(first['run_directory'])
        second=self.execute('--resume',prior)
        self.assertTrue(all('reused_from' in s for s in second['stages'].values()))
        state=json.loads((prior/'run-manifest.json').read_text())
        state['stages']['digital']['status']='running'
        (prior/'run-manifest.json').write_text(json.dumps(state))
        recovered=self.execute('--resume',prior)
        self.assertNotIn('reused_from',recovered['stages']['digital'])
        self.assertIn('reused_from',recovered['stages']['import'])
        self.assertTrue((prior/'digital/proof.epub').exists())
        (prior/'import/sections/section-0001.json').write_text('tampered')
        repaired=self.execute('--resume',prior)
        self.assertNotIn('reused_from',repaired['stages']['import'])
        (self.inputs/'book.md').write_text('# One\n\nChanged paragraph.\n',encoding='utf-8')
        changed=self.execute('--resume',Path(second['run_directory']))
        self.assertNotIn('reused_from',changed['stages']['import'])
        self.assertNotIn('reused_from',changed['stages']['digital'])
        self.cfg['selected_inputs'].append('unrelated.txt')
        (self.inputs/'unrelated.txt').write_text('unrelated')
        self.save_manifest()
        unchanged=self.execute('--resume',Path(changed['run_directory']))
        self.assertTrue(all('reused_from' in s for s in unchanged['stages'].values()))
    def test_pdf_settings_invalidate_only_pdf_branch(self):
        import reportlab
        import shutil
        font=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
        shutil.copyfile(font,self.inputs/'font.ttf')
        settings={'schema_version':1,'trim_inches':[6,9],'margins_inches':{'top':0.65,'bottom':0.65,'inner':0.7,'outer':0.6},'font':{'path':'font.ttf','embedding_authorized':True},'font_size_pt':11,'leading_pt':15,'heading_size_pt':16,'paragraph_gap_pt':6,'section_start':'new_page','footer':{'page_numbers':True,'font_size_pt':9,'offset_pt':20}}
        self.write('print.json',settings)
        self.cfg['selected_inputs'] += ['print.json','font.ttf']
        self.cfg['print_settings']='print.json'; self.save_manifest()
        stages='import,prepare,digital,pdf,audit-digital,audit-pdf'
        first=self.run_cli('--execute','--stages',stages)
        self.assertIn('runtime',first['stages']['digital']['fingerprint_components'])
        self.assertEqual(first['stages']['digital']['fingerprint_components']['packages'],{})
        self.assertTrue(first['stages']['pdf']['fingerprint_components']['packages']['reportlab']['available'])
        settings['font_size_pt']=10; self.write('print.json',settings)
        second=self.run_cli('--execute','--stages',stages,'--resume',first['run_directory'])
        for stage in ('import','prepare','digital','audit-digital'):
            self.assertIn('reused_from',second['stages'][stage])
        for stage in ('pdf','audit-pdf'):
            self.assertNotIn('reused_from',second['stages'][stage])
    def test_explicit_image_placements(self):
        import struct, zlib, zipfile
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')
        (self.inputs/'art.png').write_bytes(png)
        self.cfg['selected_inputs'].append('art.png')
        self.cfg['edition']['assets']=[{'id':'art','path':'art.png','role':'illustration','alt':'A red pixel'}]
        self.cfg['edition']['image_insertions']=[{'section_id':'section-0001','block_index':1,'asset_id':'art','caption':'Declared art'}]
        self.save_manifest()
        result=self.execute()
        root=Path(result['run_directory'])
        blocks=json.loads((root/'prepare/sections/section-0001.json').read_text())['blocks']
        self.assertEqual(blocks[0]['text'],'First paragraph.')
        self.assertEqual(blocks[1]['type'],'image')
        self.assertIn('Declared art',(root/'digital/html/index.html').read_text())
        with zipfile.ZipFile(root/'digital/proof.epub') as archive:
            self.assertTrue(any(archive.read(n)==png for n in archive.namelist() if n.endswith('.png')))
        self.cfg['edition']['image_insertions'][0]['block_index']=999
        self.save_manifest(); self.run_cli(ok=False)
    def test_no_unselected_settings_read(self):
        from unittest.mock import patch
        sys.path.insert(0,str(SCRIPTS))
        import run_project
        self.write('unselected.json',{'font':{'path':'private.ttf'}})
        self.cfg['print_settings']='unselected.json';self.save_manifest()
        original=Path.read_text
        reads=[]
        def tracked(path,*args,**kwargs):
            reads.append(path.resolve())
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',tracked):
            with self.assertRaisesRegex(ValueError,'selected'):
                run_project.load_manifest(self.manifest)
        self.assertNotIn((self.inputs/'unselected.json').resolve(),reads)
    def test_pdf_capability_gap_readonly_and_before_execute(self):
        self.write('print.json',{'font':{'path':'font.ttf'}})
        (self.inputs/'font.ttf').write_bytes(b'fixture')
        self.cfg['selected_inputs'] += ['print.json','font.ttf']
        self.cfg['print_settings']='print.json';self.save_manifest()
        command=[sys.executable,'-S','-B',str(SCRIPTS/'run_project.py'),'--manifest',str(self.manifest),'--output-root',str(self.out),'--stages','import,prepare,pdf']
        plan=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(plan.returncode,0,plan.stderr)
        value=json.loads(plan.stdout)
        self.assertTrue(value['capability_gaps'])
        self.assertTrue(value['conflicts'])
        execution=subprocess.run(command+['--execute'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(execution.returncode,2)
        self.assertEqual(list(self.out.iterdir()),[])
    def source_record(self):
        blob=(self.inputs/'book.md').read_bytes()
        return {'schema_version':1,'sources':[{'source_id':'existing-ledger-id','path':'book.md','availability':'available','sha256':digest(blob),'read_record':{'status':'partial','scope':'First five selected bytes','locator':'bytes 0:5','start_byte':0,'end_byte':5,'excerpt_sha256':digest(blob[:5])},'interpretation':'Supplied assertion','scoped_decision':'Declared application only','destinations':[{'path':'metadata.json','sha256':digest((self.inputs/'metadata.json').read_bytes()),'locator':'title','use':'production-reference'}]}]}
    def source_cli(self,name='report'):
        return self.cli('report_sources.py','--input-root',self.inputs,'--record','source-use.json','--output-root',self.out,'--output-dir',name)
    def test_sources_current_stale_unavailable_without_vault(self):
        record=self.source_record(); self.write('source-use.json',record)
        result=self.source_cli()
        report=json.loads((Path(result['output_directory'])/'source-coverage.json').read_text())
        self.assertEqual(report['sources'][0]['excerpt_verification'],'verified-selected-excerpt')
        (self.inputs/'book.md').write_text('x')
        result=self.source_cli('changed')
        source=json.loads((Path(result['output_directory'])/'source-coverage.json').read_text())['sources'][0]
        self.assertEqual(source['source_verification'],'changed-source-hash')
        self.assertEqual(source['destinations'][0]['source_provenance'],'stale-or-unavailable')
        (self.inputs/'book.md').unlink()
        result=self.source_cli('missing')
        source=json.loads((Path(result['output_directory'])/'source-coverage.json').read_text())['sources'][0]
        self.assertEqual(source['source_verification'],'missing-source-file')
        source=record['sources'][0]; source.update(path=None,availability='unavailable',sha256=None)
        source['read_record'].update(status='not-read',start_byte=None,end_byte=None,excerpt_sha256=None)
        self.write('source-use.json',record)
        self.source_cli('unavailable')

if __name__=='__main__':
    unittest.main()
