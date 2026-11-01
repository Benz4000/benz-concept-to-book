"""Real optional browser/Poppler execution and exact-release evidence recovery."""
import copy,json,os,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import verify_release as verification
import build_reading_edition as reading
from selftests.test_v11_content import build,PRINT_AVAILABLE

def reader_settings():
    path=os.environ.get('V11_READER_SETTINGS')
    if not path:
        if os.environ.get('V11_REQUIRE_READER')=='1':raise AssertionError('Actual reader settings required')
        return None
    return verification.load(path)

@unittest.skipUnless(PRINT_AVAILABLE,'Optional PDF dependencies unavailable')
class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.environ.get('BOOK_TEST_ARTIFACT_ROOT',tempfile.gettempdir()));parent.mkdir(parents=True,exist_ok=True)
        self.base=Path(tempfile.mkdtemp(prefix='v11-verify-',dir=parent));self.source,self.imported,self.out=build(self.base)
    def test_actual_html_and_epub_reader_navigation_reflow_and_relocation(self):
        settings=reader_settings()
        if not settings:self.skipTest('Existing explicit Node/playwright-core/Chromium settings unavailable')
        for kind,artifact in [('html',self.out/'digital/html/index.html'),('epub',self.out/'digital/imported-edition.epub')]:
            target=self.out/('verified-'+kind)
            report=verification.verify(artifact,kind,{'browser':settings,'required_checks':['browser','human-reader']},target)
            self.assertEqual(report['browser']['state'],'passed',report)
            self.assertEqual(report['state'],'pending');self.assertEqual(report['required_pending'],['human-reader'])
            raw=verification.load(target/'reader-probe.json');nav=[c for c in raw['checks'] if c['kind']=='navigation']
            self.assertGreaterEqual(len(nav),4);self.assertTrue(all(c['passed'] for c in nav));self.assertTrue(raw['screenshots'])
            verification.recheck(target/'verification.json')
            preview=target/raw['screenshots'][0]['path'];original=preview.read_bytes();preview.write_bytes(original+b'changed')
            with self.assertRaises(ValueError):verification.recheck(target/'verification.json')
            preview.write_bytes(original)
            if kind=='epub':
                moved=self.out/'relocated-evidence';shutil.copytree(target,moved);new_epub=self.out/'relocated.epub';shutil.copyfile(artifact,new_epub)
                verification.recheck(moved/'verification.json',new_epub)
    def test_actual_broken_navigation_is_failed(self):
        settings=reader_settings()
        if not settings:self.skipTest('Existing explicit browser settings unavailable')
        artifact=self.out/'digital/html/index.html';artifact.write_bytes(artifact.read_bytes().replace(b'href="#bm-2"',b'href="#missing"'))
        report=verification.verify(artifact,'html',{'browser':settings},self.out/'broken-reader')
        self.assertEqual(report['state'],'failed');self.assertEqual(report['browser']['state'],'failed')
    def test_actual_pdf_preflight_native_parse_render_and_wrong_geometry(self):
        renderer=os.environ.get('BOOK_TEST_PDFTOPPM');pdfinfo=os.environ.get('V11_PDFINFO') or shutil.which('pdfinfo')
        if not renderer or not pdfinfo:self.skipTest('Explicit existing Poppler tools unavailable')
        artifact=self.out/'print/imported-edition.pdf'
        settings={'pdf':{'expected_size_pt':[432,648],'pdfinfo':pdfinfo,'renderer':renderer,'pages':[1,2]},'required_checks':['pdf-local','pdf-independent','pdf-render','physical-proof']}
        report=verification.verify(artifact,'pdf',settings,self.out/'pdf-verification')
        self.assertEqual(report['pdf']['state'],'passed',report);self.assertEqual(report['pdf']['independent_parse']['state'],'passed')
        self.assertEqual(report['state'],'pending');self.assertEqual(report['required_pending'],['physical-proof'])
        self.assertTrue(report['pdf']['fonts']);verification.recheck(self.out/'pdf-verification/verification.json')
        settings['pdf']['expected_size_pt']=[300,400];settings['pdf'].pop('renderer')
        failed=verification.verify(artifact,'pdf',settings,self.out/'wrong-size');self.assertEqual(failed['state'],'failed')
    def test_unembedded_font_and_missing_capability_cannot_pass(self):
        from reportlab.pdfgen import canvas
        artifact=self.out/'unembedded.pdf';c=canvas.Canvas(str(artifact));c.drawString(50,700,'Unembedded base font.');c.save()
        report=verification.verify(artifact,'pdf',{},self.out/'bad-font');self.assertEqual(report['state'],'failed')
        html=self.out/'digital/html/index.html'
        missing=verification.verify(html,'html',{},self.out/'missing-reader');self.assertEqual(missing['state'],'pending');self.assertEqual(missing['browser']['state'],'unavailable')
    def test_observations_stale_attachments_and_changed_release(self):
        artifact=self.out/'print/imported-edition.pdf';attachment=self.out/'proof-finding.txt';attachment.write_text('Synthetic pending proof finding; no physical proof inspected.',encoding='utf-8')
        item={'id':'proof-1','method':'physical-proof','environment':'Synthetic test record only','coverage':'Uninspected physical proof','observation':'No physical test performed.','status':'unrun','limitations':'Does not establish approval.','attachments':[{'path':attachment.name,'sha256':verification.sha(attachment)}]}
        record=self.out/'observations.json';record.write_bytes(reading.encoded({'schema_version':1,'artifact_sha256':verification.sha(artifact),'checks':[item]}))
        report=verification.verify(artifact,'pdf',{'required_checks':['physical-proof']},self.out/'pending-proof',record)
        self.assertEqual(report['state'],'pending');verification.recheck(self.out/'pending-proof/verification.json')
        attachment.write_text('Changed.',encoding='utf-8')
        with self.assertRaises(ValueError):verification.recheck(self.out/'pending-proof/verification.json')
        original=verification.sha(artifact);artifact.write_bytes(artifact.read_bytes()+b'\n% changed release')
        with self.assertRaises(ValueError):verification.verify(artifact,'pdf',{},self.out/'stale-record',record)
        self.assertFalse((self.out/'stale-record').exists())
        with self.assertRaises(ValueError):verification.recheck(self.out/'pending-proof/verification.json')
        self.assertNotEqual(original,verification.sha(artifact))
    def test_refuse_overwrite_escape_and_active_content(self):
        artifact=self.out/'digital/html/index.html';target=self.out/'existing';target.mkdir();(target/'keep').write_bytes(b'preserve')
        with self.assertRaises(ValueError):verification.verify(artifact,'html',{},target)
        self.assertEqual((target/'keep').read_bytes(),b'preserve')
        for changed in [b'<html><body><script>throw 1</script></body></html>',b'<html><body><img src="../outside.png" /></body></html>']:
            artifact.write_bytes(changed)
            with self.assertRaises((ValueError,OSError)):verification.reading_snapshot(artifact,'html')

    def test_external_styles_are_refused_before_false_reader_pass(self):
        source=self.out/'remote-style';source.mkdir();artifact=source/'index.html'
        artifact.write_text('<html><head><link rel="stylesheet" href="https://example.invalid/unavailable.css"/></head><body><p>Preserved words.</p></body></html>',encoding='utf-8')
        with self.assertRaises(ValueError):verification.reading_snapshot(artifact,'html')
        artifact.write_text('<html><head><style>body {background: url(https://example.invalid/background.png)}</style></head><body><p>Preserved words.</p></body></html>',encoding='utf-8')
        with self.assertRaises(ValueError):verification.reading_snapshot(artifact,'html')

if __name__=='__main__':unittest.main()
