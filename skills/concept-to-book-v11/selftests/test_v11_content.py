"""Actual rich DOCX through all adapters; preservation, refusal and corruption."""
import contextlib,copy,io,json,os,sys,tempfile,unittest,zipfile,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import import_manuscript as imp
import import_extended_docx as extended
import build_reading_edition as reading
import build_print_edition as printing
import audit_exports as audit
import rich_content as rich
from selftests.test_semantics import META,copy_font_family

def fixture():
    w=imp.W;r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    p=lambda t:'<w:p><w:r><w:t>'+t+'</w:t></w:r></w:p>'
    heading='<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:bookmarkStart w:id="0" w:name="ChapterOne"/><w:r><w:t>The Lantern</w:t></w:r><w:bookmarkEnd w:id="0"/></w:p>'
    body='<w:p><w:bookmarkStart w:id="1" w:name="Meeting"/><w:r><w:t>The meeting changed everything.</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>'
    body+='<w:p><w:r><w:t xml:space="preserve">Revisit </w:t></w:r><w:fldSimple w:instr=" REF Meeting \\h "><w:r><w:rPr><w:i/></w:rPr><w:t>the meeting</w:t></w:r></w:fldSimple><w:r><w:t xml:space="preserve"> and </w:t></w:r><w:hyperlink w:anchor="ChapterOne"><w:r><w:t>the beginning</w:t></w:r></w:hyperlink><w:r><w:footnoteReference w:id="1"/></w:r><w:r><w:t>.</w:t></w:r></w:p>'
    body+='<w:tbl><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc>'+p('Name')+'</w:tc><w:tc>'+p('Promise')+'</w:tc></w:tr><w:tr><w:tc>'+p('Mara')+p('Keeper')+'</w:tc><w:tc>'+p('Return at dawn.')+'</w:tc></w:tr></w:tbl>'
    notes='<w:footnotes xmlns:w="'+w+'"><w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r><w:r><w:t>First source paragraph.</w:t></w:r></w:p><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Second source paragraph.</w:t></w:r></w:p></w:footnote></w:footnotes>'
    return {'[Content_Types].xml':b'<Types/>','_rels/.rels':b'<Relationships/>','word/document.xml':f'<w:document xmlns:w="{w}" xmlns:r="{r}"><w:body>{heading}{body}</w:body></w:document>'.encode(),'word/footnotes.xml':notes.encode()}

def zipped(parts):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        for k,v in parts.items():z.writestr(zipfile.ZipInfo(k,date_time=(1980,1,1,0,0,0)),v)
    return buf.getvalue()

def build(base):
    base=Path(base);source=base/'source';out=base/'out';source.mkdir();out.mkdir()
    (source/'book.docx').write_bytes(zipped(fixture()));(source/'meta.json').write_bytes(reading.encoded(META))
    args=['--input-root',str(source),'--input','book.docx','--metadata','meta.json','--output-root',str(out),'--output-dir','import','--extended-docx']
    with contextlib.redirect_stdout(io.StringIO()):assert imp.main(args)==0
    imported=out/'import'
    with contextlib.redirect_stdout(io.StringIO()):assert reading.main(['--input-root',str(imported),'--config','edition.json','--output-root',str(out),'--output-dir','digital'])==0
    settings=copy.deepcopy(printing.DEFAULTS);settings['font']=copy_font_family(imported/'fonts')
    (imported/'print.json').write_bytes(reading.encoded(settings));printing.build(imported,'edition.json','print.json',out,'print')
    return source,imported,out

PRINT_AVAILABLE=all(importlib.util.find_spec(n) is not None for n in ('reportlab','pypdf','PIL'))
@unittest.skipUnless(PRINT_AVAILABLE,'Optional PDF dependencies unavailable')
class RichContentTests(unittest.TestCase):
    def test_actual_extended_docx_three_formats_and_audits(self):
        parent=Path(os.environ.get('V11_ARTIFACT_ROOT',tempfile.gettempdir()));parent.mkdir(parents=True,exist_ok=True)
        base=Path(tempfile.mkdtemp(prefix='v11-rich-',dir=parent));source,imported,out=build(base)
        digital=audit.audit(imported,'edition.json',out/'digital');pdf=audit.audit(imported,'edition.json',out/'print','print.json')
        (base/'audits.json').write_bytes(reading.encoded({'digital':digital,'pdf':pdf}))
        self.assertTrue(digital['ok'],digital['errors']);self.assertTrue(pdf['ok'],pdf['errors'])
        cfg=json.loads((imported/'edition.json').read_bytes());sections=[dict(s,**json.loads((imported/s['source']).read_bytes())) for s in cfg['sections']]
        table=next(b for b in sections[0]['blocks'] if b['type']=='table');self.assertEqual(table['header_rows'],1)
        self.assertEqual(rich.text(table),'Name\nPromise\nMara\nKeeper\nReturn at dawn.')
        note=sections[-1]['blocks'][0];self.assertEqual(len(note['paragraphs']),2)
        self.assertEqual(note['text'],'[fn-1] First source paragraph.\nSecond source paragraph.')
        from pypdf import PdfReader
        reader=PdfReader(out/'print/imported-edition.pdf')
        self.assertGreaterEqual(sum(len(p.get('/Annots',[])) for p in reader.pages),4)
        self.assertEqual((source/'book.docx').read_bytes(),zipped(fixture()))
    def test_unsupported_table_field_bookmark_and_note_refused(self):
        original=fixture()
        changes=[('word/document.xml',b'<w:tc>',b'<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'),('word/document.xml',b'REF Meeting',b'PAGEREF Meeting'),('word/document.xml',b'w:name="Meeting"',b'w:name="ChapterOne"'),('word/document.xml',b'REF Meeting',b'REF Missing'),('word/footnotes.xml',b'</w:footnote>',b'<w:tbl/></w:footnote>')]
        for part,a,b in changes:
            parts=dict(original);parts[part]=parts[part].replace(a,b)
            with self.subTest(change=b),self.assertRaises((ValueError,imp.Refusal)):
                units,issues,_=extended.parse(zipped(parts),imp)
                if issues:raise imp.Refusal(str(issues))
                imp.convert(units)
    def test_preflight_no_writes_strict_legacy_refusal_and_preservation(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);s=base/'source';o=base/'out';s.mkdir();o.mkdir();data=zipped(fixture())
            (s/'book.docx').write_bytes(data);(s/'meta.json').write_bytes(reading.encoded(META))
            common=['--input-root',str(s),'--input','book.docx','--metadata','meta.json','--output-root',str(o),'--output-dir','probe']
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(imp.main(common+['--extended-docx','--preflight']),0)
                self.assertEqual(imp.main(common),2)
            self.assertEqual(list(o.iterdir()),[]);self.assertEqual((s/'book.docx').read_bytes(),data)
    def test_actual_export_table_or_note_corruption_fails(self):
        with tempfile.TemporaryDirectory() as t:
            _,imported,out=build(t);html=out/'digital/html/index.html'
            original=html.read_bytes()
            for a,b in [(b'Return at dawn.',b'Return at dusk.'),(b'Second source paragraph.',b'Altered source paragraph.'),(b'#bm-2',b'#bm-1')]:
                self.assertIn(a,original);html.write_bytes(original.replace(a,b))
                self.assertFalse(audit.audit(imported,'edition.json',out/'digital')['ok'])
            html.write_bytes(original)
    def test_oversized_table_refuses_without_partial_pdf(self):
        with tempfile.TemporaryDirectory() as t:
            _,imported,out=build(t);p=imported/'sections/section-0001.json';obj=json.loads(p.read_bytes())
            table=next(b for b in obj['blocks'] if b['type']=='table');table['rows']+=copy.deepcopy(table['rows'][1:])*70
            p.write_bytes(reading.encoded(obj))
            with self.assertRaises(reading.BuildError):printing.build(imported,'edition.json','print.json',out,'oversized')
            self.assertFalse((out/'oversized').exists())
    def test_connected_runner_extended_import_and_recovery(self):
        import run_project
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);source=base/'source';out=base/'out';source.mkdir();out.mkdir()
            data=zipped(fixture());(source/'book.docx').write_bytes(data);(source/'metadata.json').write_bytes(reading.encoded(META))
            cfg={'schema_version':1,'input_root':str(source),'selected_inputs':['book.docx','metadata.json'],'import':{'manuscript':'book.docx','metadata':'metadata.json','extended_docx':True},'edition':{'edition_id':'rich-run','formats':['html','epub'],'sections':[{'id':'section-0001','part':'body','kind':'chapter'},{'id':'section-0002','part':'back','kind':'endnotes'}],'assets':[]}}
            config=base/'project.json';config.write_bytes(reading.encoded(cfg));stages=['import','prepare','digital','audit-digital']
            plan=run_project.run(config,out,stages);self.assertFalse(plan['conflicts']);self.assertEqual(list(out.iterdir()),[])
            first=run_project.run(config,out,stages,True);second=run_project.run(config,out,stages,True,first['run_directory'])
            self.assertTrue(all(s.get('reused_from') for s in second['stages'].values()));self.assertEqual((source/'book.docx').read_bytes(),data)
    def test_real_epubcheck_extended_output(self):
        jar=os.environ.get('V10_EPUBCHECK_JAR');java=os.environ.get('V10_JAVA')
        if not jar or not java:
            if os.environ.get('V10_REQUIRE_EPUBCHECK')=='1':self.fail('Actual EPUBCheck required')
            self.skipTest('Explicit existing EPUBCheck distribution unavailable')
        import validate_digital
        parent=Path(os.environ.get('BOOK_TEST_ARTIFACT_ROOT',tempfile.gettempdir()));base=Path(tempfile.mkdtemp(prefix='v11-epubcheck-',dir=parent));_,_,out=build(base)
        result=validate_digital.validate(out/'digital/imported-edition.epub',out/'validation',{'jar':jar,'java':java})
        self.assertEqual(result['automated_validation']['state'],'passed',result)
        structured=result['automated_validation']['structured_result'];self.assertEqual(structured['nWarning'],0);self.assertEqual(structured['nError'],0)

    def test_note_relationship_scope_refused_without_borrowing_document_ids(self):
        import xml.etree.ElementTree as ET
        parts=fixture();w=imp.W;r='http://schemas.openxmlformats.org/officeDocument/2006/relationships';q=lambda n:'{'+w+'}'+n
        parts['word/_rels/document.xml.rels']=('<Relationships><Relationship Id="rOutside" Type="'+r+'/hyperlink" Target="https://example.invalid/wrong-part" TargetMode="External"/></Relationships>').encode()
        root=ET.fromstring(parts['word/footnotes.xml']);p=root[0][0];p.clear()
        h=ET.SubElement(p,q('hyperlink'),{'{'+r+'}id':'rOutside'});ET.SubElement(ET.SubElement(h,q('r')),q('t')).text='First source paragraph.'
        parts['word/footnotes.xml']=ET.tostring(root)
        with self.assertRaises(imp.Refusal):extended.parse(zipped(parts),imp)

if __name__=='__main__':unittest.main()
