"""Substantial synthetic book: real runner, editions, revision, covers and evidence."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
STAGES='import,prepare,digital,pdf,audit-digital,audit-pdf'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def data_sha(value):return hashlib.sha256(value).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2),encoding='utf-8')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in Path(root).rglob('*') if p.is_file()}

def manuscript():
    paragraphs=['# For the Watchers','This is a synthetic book used only to test production and revision.']
    passage=('Mara watched the evening tide move between the harbor stones. Each returning boat carried a different account of the crossing, and she wrote the differences in her ledger before asking the keeper another question. The answers did not settle the matter. A light remained on the farther bank, where the abandoned station faced the channel. She would examine the charts, speak with the waiting families, and make her choice before the weather closed the passage. What she learned would change how the harbor understood its own promises.')
    for chapter in range(1,31):
        paragraphs += [f'# Chapter {chapter}: The Lantern Beyond the Harbor and the Promise That Remained',f'## Evening watch {chapter}']
        for number in range(24):
            if number==8:paragraphs.append('***')
            if number==16:paragraphs.append(f'### The second account in chapter {chapter}')
            text=f'Record {chapter}-{number+1}. '+passage
            if number%7==0:text += ' She remembered *the promise* and answered with **deliberate care**.'
            if chapter==15 and number==12:text += ' MIDBOOK-ORIGINAL: she kept the brass key.'
            paragraphs.append(text)
    paragraphs += ['# Afterword','This synthetic manuscript contains no historical assertions or real author biography. The scene repetitions test pagination and dependency handling, not literary quality.']
    return '\n\n'.join(paragraphs)+'\n'

@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('reportlab','pypdf','PIL')), 'Optional print dependencies unavailable')
class BookScale(unittest.TestCase):
    def setUp(self):
        self.temp=None
        retained=os.environ.get('BOOK_TEST_ARTIFACT_ROOT')
        if retained:self.work=Path(tempfile.mkdtemp(prefix='book-scale-',dir=retained))
        else:
            self.temp=tempfile.TemporaryDirectory(prefix='book-scale-')
            self.work=Path(self.temp.name)/'work';self.work.mkdir()
        self.source=self.work/'source';self.source.mkdir()
        self.out=self.work/'releases';self.out.mkdir()
        self.logs=self.work/'logs';self.logs.mkdir();self.counter=0
        self.renderer=os.environ.get('BOOK_TEST_PDFTOPPM') or shutil.which('pdftoppm')
        if not self.renderer:self.skipTest('Actual PDF renderer unavailable')

    def tearDown(self):
        if self.temp:self.temp.cleanup()

    def cli(self,script,args,success=True):
        self.counter+=1
        command=[sys.executable,'-B',str(ROOT/'scripts'/script),*map(str,args)]
        result=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'},timeout=300)
        write(self.logs/f'{self.counter:02d}-{Path(script).stem}.json',{'command':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if success:self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        else:self.assertNotEqual(result.returncode,0)
        return json.loads(result.stdout) if result.stdout.strip().startswith('{') else result.stdout

    def run_book(self,project,resume=None):
        args=['--manifest',project,'--output-root',self.out,'--stages',STAGES,'--execute']
        if resume:args+=['--resume',resume]
        result=self.cli('run_project.py',args)
        self.assertEqual(result['status'],'complete')
        return Path(result['run_directory']),result

    def review(self,pdf,name,pages,previous=None):
        inputs=self.work/('render-input-'+name);inputs.mkdir()
        shutil.copyfile(pdf,inputs/'proof.pdf')
        cfg={'schema_version':1,'pdf':'proof.pdf','renderer':str(self.renderer),'pages':pages,'dpi':48}
        if previous:cfg['previous_manifest']=str(previous)
        path=inputs/'review.json';write(path,cfg)
        self.cli('render_review.py',['--config',path,'--output-dir',self.out/name])
        return self.out/name/'manifest.json'

    def test_substantial_book_revision_and_independent_editions(self):
        from selftests.test_semantics import copy_font_family
        from PIL import Image,ImageDraw
        from pypdf import PdfReader
        font=copy_font_family(self.source/'fonts')
        content=manuscript();(self.source/'manuscript.md').write_text(content,encoding='utf-8')
        words=len(content.split());self.assertGreater(words,60000)
        write(self.source/'metadata.json',{'title':'The Harbor Ledger','author':'Synthetic Fixture','identifier':'urn:test:harbor-v9','language':'en','modified':'2026-10-31T00:00:00Z'})
        art=self.source/'art';art.mkdir()
        image=Image.new('RGB',(600,900),(242,229,191));draw=ImageDraw.Draw(image)
        for y in range(660,900,30):draw.rectangle((0,y,599,y+10),fill=(91,143,155))
        image.save(art/'front.png')
        Image.new('RGB',(500,120),(181,205,211)).save(art/'map.png')
        settings=read(ROOT/'assets/templates/print-settings.json');settings['font']=font
        write(self.source/'print-settings.json',settings)
        sections=[{'id':f'section-{i:04d}','part':'front' if i==1 else 'back' if i==32 else 'body','kind':'preface' if i==1 else 'afterword' if i==32 else 'chapter'} for i in range(1,33)]
        assets=[{'id':'front-art','path':'art/front.png','role':'front-cover','alt':'Synthetic coastal color bands.'},{'id':'route-art','path':'art/map.png','role':'map','alt':'Synthetic pale blue map placeholder; no real geography.'}]
        project={'schema_version':1,'input_root':str(self.source),'selected_inputs':[p.relative_to(self.source).as_posix() for p in self.source.rglob('*') if p.is_file()],
                 'import':{'manuscript':'manuscript.md','metadata':'metadata.json'},'edition':{'edition_id':'harbor-paperback','formats':['html','epub'],'sections':sections,'assets':assets,'cover_image':'front-art',
                 'image_insertions':[{'section_id':f'section-{i:04d}','block_index':1,'asset_id':'route-art','caption':'Synthetic fixture illustration.'} for i in (2,8,15,22,30)]},'print_settings':'print-settings.json'}
        project_path=self.work/'project.json';write(project_path,project)
        original=inventory(self.source)
        plan=self.cli('run_project.py',['--manifest',project_path,'--output-root',self.out,'--stages',STAGES])
        self.assertFalse(plan['conflicts']);self.assertFalse(plan['missing_inputs']);self.assertFalse(list(self.out.iterdir()))
        first,first_result=self.run_book(project_path)
        pdf=first/'pdf/harbor-paperback.pdf';pages=len(PdfReader(pdf).pages);self.assertGreater(pages,150)
        first_tree=inventory(first)
        self.assertEqual(original,inventory(self.source))
        layout=read(first/'pdf/build-manifest.json')
        middle=next(row['start_page'] for row in layout['section_placements'] if row['id']=='section-0016')
        selected=sorted({1,2,middle,min(middle+1,pages),pages})
        review1=self.review(pdf,'review-before',selected)

        # A second physical edition shares the source but has independently chosen layout.
        hardcover=self.work/'hardcover-source';shutil.copytree(self.source,hardcover)
        hc_settings=read(hardcover/'print-settings.json');hc_settings['trim_inches']=[6.5,9.5];write(hardcover/'print-settings.json',hc_settings)
        hc_project=json.loads(json.dumps(project));hc_project['input_root']=str(hardcover);hc_project['edition']['edition_id']='harbor-hardcover'
        hc_path=self.work/'hardcover.json';write(hc_path,hc_project)
        hc,hc_result=self.run_book(hc_path)
        hc_tree=inventory(hc);self.assertNotEqual(len(PdfReader(hc/'pdf/harbor-hardcover.pdf').pages),pages)

        # Print-only settings change must retain the exact import/digital branch.
        revised_settings=read(self.source/'print-settings.json');revised_settings['paragraph_gap_pt']=7;write(self.source/'print-settings.json',revised_settings)
        changed_layout,layout_result=self.run_book(project_path,first)
        for stage in ('import','prepare','digital','audit-digital'):self.assertIn('reused_from',layout_result['stages'][stage])
        for stage in ('pdf','audit-pdf'):self.assertNotIn('reused_from',layout_result['stages'][stage])
        self.assertEqual(hc_tree,inventory(hc));self.assertEqual(first_tree,inventory(first))

        # Changed manuscript and simulated incomplete checkpoint: recover into a new run.
        (self.source/'manuscript.md').write_text(content.replace('MIDBOOK-ORIGINAL: she kept the brass key.','MIDBOOK-REVISED: she returned the brass key to its keeper.'),encoding='utf-8')
        checkpoint=self.out/'interrupted-checkpoint';shutil.copytree(changed_layout,checkpoint)
        state=read(checkpoint/'run-manifest.json');state['status']='running';state['stages']['pdf']['status']='running';write(checkpoint/'run-manifest.json',state)
        checkpoint_tree=inventory(checkpoint)
        revised,result=self.run_book(project_path,checkpoint)
        self.assertEqual(checkpoint_tree,inventory(checkpoint));self.assertNotIn('reused_from',result['stages']['import'])
        revised_pdf=revised/'pdf/harbor-paperback.pdf'
        self.cli('audit_exports.py',['--input-root',revised/'pdf-input','--config','edition.json','--settings','print-settings.json','--release-root',first/'pdf'],success=False)
        self.assertEqual(first_tree,inventory(first));self.assertEqual(hc_tree,inventory(hc))
        # Hardcover remains an unchanged historical release, not automatically current after a shared prose revision.
        review2=self.review(revised_pdf,'review-after',selected,review1)
        review_data=read(review2);self.assertTrue(review_data['changed_pages'])
        self.assertNotEqual(read(review1)['pdf']['sha256'],review_data['pdf']['sha256'])

        # Cover uses supplied test geometry, never a guessed spine formula.
        cover_root=self.work/'cover-input';cover_root.mkdir()
        shutil.copyfile(pdf,cover_root/'interior.pdf');shutil.copyfile(self.source/'fonts/Vera.ttf',cover_root/'regular.ttf')
        shutil.copyfile(art/'front.png',cover_root/'front.png')
        barcode=Image.new('RGB',(240,80),'white');bd=ImageDraw.Draw(barcode)
        for x in range(4,232,8):bd.rectangle((x,4,x+3,70),fill='black')
        barcode.save(cover_root/'barcode-fixture.png')
        template={'schema_version':1,'units':'pt','edition':'harbor-paperback','page_count':pages,'sheet':[918,666],
                  'panels':{'back':{'trim':[9,9,432,648],'bleed':[0,0,450,666],'safe':[27,27,396,612]},'spine':{'trim':[441,9,36,648],'bleed':[441,0,36,666],'safe':[447,27,24,612]},'front':{'trim':[477,9,432,648],'bleed':[468,0,450,666],'safe':[495,27,396,612]}}}
        write(cover_root/'template.json',template)
        cfg={'schema_version':1,'template':'template.json','interior':{'path':'interior.pdf','sha256':sha(pdf),'page_count':pages,'edition':'harbor-paperback'},'fonts':[{'id':'regular','path':'regular.ttf','embedding_authorized':True}],
             'images':[{'id':'front','path':'front.png','role':'art','panel':'front','box':[477,9,432,648],'usage_authorized':True},{'id':'barcode','path':'barcode-fixture.png','role':'barcode','panel':'back','box':[27,27,120,40],'usage_authorized':True}],
             'texts':[{'id':'title','text':'The Harbor Ledger','font':'regular','panel':'front','box':[513,492,360,100],'font_size_pt':25,'leading_pt':32,'rotation':0},{'id':'blurb','text':'A synthetic cover proof for the workflow test. The supplied geometry and barcode pattern are test fixtures, not manufacturing approval.','font':'regular','panel':'back','box':[45,400,360,160],'font_size_pt':13,'leading_pt':18,'rotation':0}]}
        write(cover_root/'cover.json',cfg)
        self.cli('build_cover.py',['--config',cover_root/'cover.json','--output-dir',self.out/'cover-before'])
        cover_manifest=self.out/'cover-before/manifest.json'
        sys.path.insert(0,str(ROOT/'scripts'))
        import build_cover
        with self.assertRaises(Exception):build_cover.validate_cover_pair(cover_manifest,revised_pdf)
        cover_pdf=self.out/'cover-before/cover.pdf'
        self.review(cover_pdf,'cover-review',[1])
        write(self.work/'scale-summary.json',{'words':words,'sections':32,'paperback_pages':pages,'hardcover_pages':len(PdfReader(hc/'pdf/harbor-hardcover.pdf').pages),
             'revised_paperback_pages':len(PdfReader(revised_pdf).pages),'first_run':str(first),'revised_run':str(revised),'hardcover_run':str(hc),
             'visual_review_before':str(review1),'visual_review_after':str(review2),'cover_manifest':str(cover_manifest),
             'asserted':'Actual local import/build/audit/revision/resume, selected-page rendering and changed-interior cover-pair refusal. No human/full-book/printer acceptance inferred.'})

if __name__=='__main__':unittest.main()
