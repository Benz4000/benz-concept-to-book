"""Actual V10 optional pipeline, interruption, edition isolation and EPUBCheck regressions."""
import copy
import gc
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import run_project as runner
import validate_digital

BASE=Path(os.environ['BOOK_TEST_ARTIFACT_ROOT'])/'pipeline' if os.environ.get('BOOK_TEST_ARTIFACT_ROOT') else Path(tempfile.gettempdir())/'concept-to-book-v10-pipeline'
JAVA=os.environ.get('V10_JAVA') or shutil.which('java') or 'java'
JAR=os.environ.get('V10_EPUBCHECK_JAR')
RENDERER=os.environ.get('BOOK_TEST_PDFTOPPM') or shutil.which('pdftoppm')


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.root=BASE/('case-'+uuid.uuid4().hex); self.inputs=self.root/'selected'; self.out=self.root/'outputs'
        self.inputs.mkdir(parents=True); self.out.mkdir()
        (self.inputs/'book.md').write_text('# One\n\nA small local proof.\n',encoding='utf-8')
        self.write('metadata.json',{'title':'Pipeline proof','author':'Author','identifier':'urn:test:pipeline','language':'en','modified':'2026-10-31T00:00:00Z'})
        self.cfg={'schema_version':1,'input_root':str(self.inputs),'selected_inputs':['book.md','metadata.json'],'import':{'manuscript':'book.md','metadata':'metadata.json'},'edition':{'edition_id':'proof','formats':['html','epub'],'assets':[],'sections':[{'id':'section-0001','part':'body','kind':'chapter'}]}}
        self.manifest=self.root/'project.json'; self.save()
    def write(self,name,value):
        (self.inputs/name).write_bytes(runner.encoded(value))
    def save(self): self.manifest.write_bytes(runner.encoded(self.cfg))
    def execute(self,stages,resume=None):
        self.save(); return runner.run(self.manifest,self.out,stages.split(','),True,resume)
    def preserve_run_for_relocation(self,current):
        # Windows scanners can briefly deny a directory rename after many newly
        # generated PDFs/previews. Retry only sharing/access errors, without
        # allowing the relocation assertion to pass while the old path exists.
        boundary=self.root.resolve(strict=True)
        allowed=BASE.resolve(strict=True)
        output=self.out.resolve(strict=True)
        source=current.resolve(strict=True)
        target=output/('preserved-'+source.name)
        self.assertTrue(boundary.is_relative_to(allowed) and output.is_relative_to(boundary))
        self.assertEqual(source.parent,output)
        self.assertTrue(source.name.startswith('run-') and source.is_dir() and not current.is_symlink())
        self.assertEqual(target.resolve().parent,output)
        self.assertFalse(target.exists())
        before=runner.inventory(source)
        attempts=[]
        for delay in (0,.1,.25,.5,1,2):
            if delay:
                gc.collect()
                time.sleep(delay)
            # Recheck both exact resolved paths before every recursive move.
            self.assertEqual(source.resolve(strict=True).parent,output)
            self.assertTrue(source.resolve().is_relative_to(boundary) and target.resolve().is_relative_to(boundary))
            self.assertFalse(target.exists())
            try:
                source.rename(target)
                attempts.append({'outcome':'renamed','delay_seconds':delay})
                break
            except PermissionError as exc:
                attempts.append({'outcome':'denied','winerror':getattr(exc,'winerror',None),'delay_seconds':delay})
                if os.name!='nt' or getattr(exc,'winerror',None) not in (5,32,33) or delay==2:
                    raise
        self.assertFalse(source.exists())
        self.assertEqual(runner.inventory(target),before)
        (self.root/'relocation-rename-evidence.json').write_bytes(runner.encoded({'source':str(source),'preserved_target':str(target),'attempts':attempts,'preserved_inventory':before}))
        return target
    def add_print(self):
        import reportlab
        shutil.copyfile(Path(reportlab.__file__).parent/'fonts/Vera.ttf',self.inputs/'font.ttf')
        settings={'schema_version':1,'trim_inches':[6,9],'margins_inches':{'top':.65,'bottom':.65,'inner':.7,'outer':.6},'font':{'path':'font.ttf','embedding_authorized':True},'font_size_pt':11,'leading_pt':15,'heading_size_pt':16,'paragraph_gap_pt':6,'section_start':'new_page','footer':{'page_numbers':True,'font_size_pt':9,'offset_pt':20}}
        self.write('print.json',settings); self.cfg['selected_inputs']+=['print.json','font.ttf']; self.cfg['print_settings']='print.json'
    def add_cover(self):
        from PIL import Image
        Image.new('RGB',(600,900),'#335577').save(self.inputs/'art.png')
        Image.new('RGB',(200,100),'white').save(self.inputs/'barcode.png')
        template={'schema_version':1,'units':'in','edition':'paperback','page_count':1,'sheet':[12.75,9.25],'panels':{'back':{'trim':[.125,.125,6,9],'bleed':[0,0,6.25,9.25],'safe':[.375,.375,5.5,8.5]},'spine':{'trim':[6.125,.125,.5,9],'bleed':[6.125,0,.5,9.25],'safe':[6.225,.375,.3,8.5]},'front':{'trim':[6.625,.125,6,9],'bleed':[6.5,0,6.25,9.25],'safe':[6.875,.375,5.5,8.5]}}}
        self.write('template.json',template)
        cover={'schema_version':1,'template':'template.json','interior':{'path':'runner-binds-current-interior.pdf','sha256':'0'*64,'page_count':1,'edition':'paperback'},'fonts':[{'id':'body','path':'font.ttf','embedding_authorized':True}],'images':[{'id':'front','path':'art.png','role':'art','panel':'front','box':[6.625,.125,6,9],'usage_authorized':True},{'id':'barcode','path':'barcode.png','role':'barcode','panel':'back','box':[3.5,.6,2,1],'usage_authorized':True}],'texts':[{'id':'title','text':'LOCAL PROOF','font':'body','panel':'front','box':[7,7,5,1],'font_size_pt':24,'leading_pt':28}]}
        self.write('cover.json',cover); self.cfg['selected_inputs']+=['cover.json','template.json','art.png','barcode.png']; self.cfg['covers']=[{'id':'paperback','config':'cover.json'}]
    def test_real_validator_and_reader_separation(self):
        settings={'java':JAVA,'jar':JAR}
        if not validate_digital.capability(settings)['available']:
            if os.environ.get('V10_REQUIRE_EPUBCHECK')=='1': self.fail('Required real EPUBCheck unavailable')
            self.skipTest('EPUBCheck unavailable; set V10_EPUBCHECK_JAR and V10_JAVA')
        self.cfg['validation']={'validator':settings}
        # EPUBCheck 5.4.0 abbreviates any matching cwd string prefix, including
        # sibling names (out vs outputs). The adapter must select its own cwd.
        prefix_cwd=self.root/'out'; prefix_cwd.mkdir()
        previous_cwd=Path.cwd()
        try:
            os.chdir(prefix_cwd)
            result=self.execute('import,prepare,digital,validate-digital')
        finally:
            os.chdir(previous_cwd)
        run=Path(result['run_directory']); value=runner.strict_json(run/'validate-digital/validation.json')
        self.assertEqual(value['automated_validation']['state'],'passed')
        self.assertEqual(Path(value['automated_validation']['working_directory']),run/'digital')
        self.assertIn('5.4.0',value['validator']['version'])
        self.assertEqual(value['reader_checks']['state'],'unrun')
        self.assertEqual(value['accessibility_state'],'not-established')
        report=runner.strict_json(run/'validate-digital/epubcheck-report.json')
        report['checker']['path']=str(self.root/'another.epub')
        self.write('wrong-target-report.json',report)
        with self.assertRaisesRegex(ValueError,'different EPUB'):
            validate_digital.structured_report(self.inputs/'wrong-target-report.json',run/'digital/proof.epub',value['validator']['version'])
        self.write('malformed-report.json',{'checker':{},'messages':[]})
        with self.assertRaisesRegex(ValueError,'Malformed'):
            validate_digital.structured_report(self.inputs/'malformed-report.json',run/'digital/proof.epub',value['validator']['version'])
        original=run/'digital/proof.epub'; broken=self.root/'broken.epub'
        with zipfile.ZipFile(original) as src,zipfile.ZipFile(broken,'w') as dst:
            for name in src.namelist():
                blob=src.read(name)
                if name.endswith('.opf'): blob=blob.replace(b'application/xhtml+xml',b'application/unknown-type')
                dst.writestr(name,blob)
        bad=validate_digital.validate(broken,self.out/'broken-validation',settings)
        self.assertEqual(bad['automated_validation']['state'],'failed')
        checks=[{'area':area,'method':'human-reader','viewer':'Declared reader','environment':'Declared OS','coverage':'First section only','observation':'Supplied observation','status':'passed','limitations':'Sample coverage only'} for area in sorted(validate_digital.AREAS)]
        self.write('reader.json',{'schema_version':1,'epub_sha256':'0'*64,'checks':checks})
        value=validate_digital.validate(original,self.out/'stale-reader',{},self.inputs/'reader.json')
        self.assertEqual(value['reader_checks']['state'],'stale')
        self.assertEqual(value['automated_validation']['state'],'unavailable')
    def test_unavailable_validator_and_readonly_plan(self):
        self.cfg['validation']={'validator':{'java':'missing-java-command','jar':'C:/missing-epubcheck.jar'}}; self.save()
        before=list(self.out.iterdir()); plan=runner.run(self.manifest,self.out,['import','prepare','digital','validate-digital'])
        self.assertFalse(plan['optional_tools']['validate-digital']['epubcheck']['available']); self.assertEqual(before,list(self.out.iterdir()))
        result=self.execute('import,prepare,digital,validate-digital'); value=runner.strict_json(Path(result['run_directory'])/'validate-digital/validation.json')
        self.assertEqual(value['automated_validation']['state'],'unavailable')
    def test_cover_render_recovery_stale_pair_and_independent_edition(self):
        if not RENDERER: self.skipTest('Actual pdftoppm unavailable; set BOOK_TEST_PDFTOPPM')
        from build_cover import validate_cover_pair
        self.add_print(); self.add_cover()
        self.write('render.json',{'schema_version':1,'pdf':'runner-binds.pdf','pages':[1],'dpi':36,'renderer':RENDERER})
        self.cfg['selected_inputs'].append('render.json'); self.cfg['renders']=[{'id':'interior','target':'pdf','config':'render.json'},{'id':'wrap','target':'cover:paperback','config':'render.json'}]
        self.cfg['reviews']=[{'id':'interior','target':'pdf','packets':['interior']},{'id':'wrap','target':'cover:paperback','packets':['wrap']}]
        self.cfg['package']={'stages':['digital','pdf','cover','render','review'],'required_reviews':['interior','wrap']}
        stages='import,prepare,digital,pdf,cover,render,review,package'
        first=self.execute(stages); old=Path(first['run_directory']); old_hashes=runner.inventory(old)
        package=runner.strict_json(old/'package/package-manifest.json'); self.assertEqual(package['status'],'local-candidate'); self.assertEqual(package['review_state'],'pending')
        state=runner.strict_json(old/'run-manifest.json'); state['stages']['render']['status']='running'; state['status']='incomplete'; (old/'run-manifest.json').write_bytes(runner.encoded(state))
        recovered=self.execute(stages,old); fresh=Path(recovered['run_directory'])
        self.assertNotIn('reused_from',recovered['stages']['render']); self.assertIn('reused_from',recovered['stages']['cover'])
        self.assertEqual(runner.sha((old/'cover/paperback/cover.pdf').read_bytes()),old_hashes['cover/paperback/cover.pdf'])
        (self.inputs/'book.md').write_text('# One\n\nThe exact interior has changed.\n',encoding='utf-8')
        changed=self.execute(stages,fresh); current=Path(changed['run_directory'])
        self.assertNotIn('reused_from',changed['stages']['cover']); self.assertNotIn('reused_from',changed['stages']['render'])
        with self.assertRaisesRegex(Exception,'invalidated'):
            validate_cover_pair(old/'cover/paperback/manifest.json',current/'pdf/proof.pdf')
        validate_cover_pair(current/'cover/paperback/manifest.json',current/'pdf/proof.pdf')
        prior_bytes=(current/'cover/paperback/cover.pdf').read_bytes()
        self.cfg['edition']['edition_id']='independent-reading'; independent=self.execute('import,prepare,digital',current)
        self.assertEqual((current/'cover/paperback/cover.pdf').read_bytes(),prior_bytes)
        self.assertTrue((Path(independent['run_directory'])/'digital/independent-reading.epub').is_file())
        from pipeline_extensions import validate_package
        relocated=self.root/'relocated-candidate'; shutil.copytree(current/'package',relocated)
        self.preserve_run_for_relocation(current)
        self.assertFalse(current.exists())
        self.assertEqual(validate_package(relocated/'package-manifest.json')['review_state'],'pending')
        preview=next((relocated/'evidence').glob('review-*/packet-*/page-*.png'))
        preview.write_bytes(b'changed preview')
        with self.assertRaisesRegex(ValueError,'payload changed'):
            validate_package(relocated/'package-manifest.json')
    def test_source_report_uses_explicit_snapshot_and_output_destinations(self):
        self.cfg['source_report']={'record':'source-use.json','stages':['digital']}
        source={'source_id':'ledger-existing','path':'inputs/book.md','availability':'available','sha256':runner.sha((self.inputs/'book.md').read_bytes()),'read_record':{'status':'not-read','scope':'No reading claim','locator':'whole supplied file','start_byte':None,'end_byte':None,'excerpt_sha256':None},'interpretation':'Declared source','scoped_decision':'Preserve supplied prose','destinations':[{'path':'outputs/digital/proof.epub','sha256':'0'*64,'locator':'Section One','use':'declared-application'}]}
        self.write('source-use.json',{'schema_version':1,'sources':[source]}); self.cfg['selected_inputs'].append('source-use.json')
        self.cfg['package']={'stages':['digital','source-report'],'required_reviews':[]}
        result=self.execute('import,prepare,digital,source-report,package'); record=runner.strict_json(Path(result['run_directory'])/'source-report/report/source-coverage.json')
        self.assertEqual(record['sources'][0]['source_verification'],'verified-file-access'); self.assertEqual(record['sources'][0]['destinations'][0]['verification'],'changed-destination-hash')
        package=runner.strict_json(Path(result['run_directory'])/'package/package-manifest.json')
        self.assertTrue(any(f['area']=='source-coverage' for f in package['readiness_findings']))
        self.assertEqual(package['review_state'],'pending')
    def test_extension_unselected_asset_is_not_read(self):
        self.add_print(); self.add_cover(); self.cfg['selected_inputs'].remove('art.png'); self.save()
        with self.assertRaisesRegex(ValueError,'selected'): runner.load_manifest(self.manifest)
    @unittest.skipUnless(os.name=='nt','Native Windows sharing-lock regression')
    def test_windows_sharing_lock_during_preserving_rename(self):
        import ctypes
        import threading
        from ctypes import wintypes
        source=self.out/'run-sharing-lock'; source.mkdir()
        (source/'preserved.txt').write_text('Exact retained fixture',encoding='utf-8')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CloseHandle.restype=wintypes.BOOL
        # A native descendant handle permits reads but withholds delete sharing,
        # preventing folder rename until closed, as an active scanner may do.
        handle=kernel.CreateFileW(str(source/'preserved.txt'),0x80000000,1,None,3,128,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value,ctypes.get_last_error())
        released=threading.Event()
        def release():
            if not released.is_set():
                kernel.CloseHandle(handle)
                released.set()
        timer=threading.Timer(.2,release); timer.start()
        try:
            preserved=self.preserve_run_for_relocation(source)
        finally:
            timer.cancel(); timer.join(); release()
        evidence=runner.strict_json(self.root/'relocation-rename-evidence.json')
        self.assertTrue(any(item['outcome']=='denied' and item['winerror'] in (5,32,33) for item in evidence['attempts']))
        self.assertFalse(source.exists())
        self.assertEqual((preserved/'preserved.txt').read_text(encoding='utf-8'),'Exact retained fixture')

if __name__=='__main__': unittest.main()
