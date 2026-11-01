#!/usr/bin/env python3
"""V11 repeatable local reader/PDF checks and exact-release observation records.

Python 3.12+. Optional browser: explicit Node, playwright-core module, Chromium.
PDF: pypdf; optional actual Poppler pdfinfo and rendered page evidence.
No download, installation, publication, external URL fetch or inferred approval.
"""
from __future__ import annotations
import argparse,hashlib,io,json,os,posixpath,re,shutil,subprocess,sys,tempfile
from pathlib import Path,PurePosixPath
from urllib.parse import unquote,urlsplit
import xml.etree.ElementTree as ET
import zipfile
import build_reading_edition as reading

VERSION='1.0.0';need=reading.need
LIMIT=128*1024*1024
def sha(p):return reading.sha(Path(p).read_bytes())
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'),object_pairs_hook=reading.unique_object)
def file_record(p):
    p=Path(p).resolve(strict=True);need(p.is_file() and p.stat().st_size<=LIMIT,'Missing or oversized evidence file')
    return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def parse_xml(data):
    need(b'<!ENTITY' not in data.upper() and not re.search(br'<!DOCTYPE\s+(?!html\s*>)[^>]+',data,re.I),'External DTD/entities unsupported')
    return ET.fromstring(data)
def safe_name(name):
    need(isinstance(name,str) and name and '\\' not in name and ':' not in name and not name.startswith('/') and all(x not in ('','.','..') for x in name.split('/')),'Unsafe archive/resource path')
    return name
def local_resource(base,href):
    url=urlsplit(href)
    if url.scheme or url.netloc:return None
    name=posixpath.normpath(posixpath.join(posixpath.dirname(base),unquote(url.path))) if url.path else base
    return safe_name(name)

def reading_snapshot(artifact,kind):
    resources={};source_files=[]
    if kind=='epub':
        with zipfile.ZipFile(artifact) as archive:
            members=archive.infolist()
            need(len(members)<=2000 and sum(i.file_size for i in members)<=LIMIT and all(i.file_size<=32*1024*1024 for i in members),'EPUB expansion limits exceeded')
            names=[i.filename for i in members if not i.is_dir()]
            need(len(names)==len(set(names)),'Duplicate EPUB members')
            for n in names:resources[safe_name(n)]=archive.read(n)
        container=parse_xml(resources['META-INF/container.xml']);roots=[n.get('full-path') for n in container.iter() if n.tag.split('}')[-1]=='rootfile']
        need(len(roots)==1,'Expected one EPUB rootfile');opf_name=safe_name(roots[0]);opf=parse_xml(resources[opf_name])
        items={};nav=[]
        for n in opf.iter():
            if n.tag.split('}')[-1]=='item':
                identity=n.get('id');need(identity and identity not in items,'Duplicate EPUB manifest ID')
                items[identity]=local_resource(opf_name,n.get('href',''))
                if 'nav' in n.get('properties','').split():nav.append(items[identity])
        docs=[items[n.get('idref')] for n in opf.iter() if n.tag.split('}')[-1]=='itemref']
        need(len(nav)==1 and docs and len(docs)==len(set(docs)),'EPUB needs one nav and unique spine documents')
        documents=list(dict.fromkeys(nav+docs))
    else:
        root=artifact.parent;pending=[artifact.name];documents=[]
        while pending:
            name=pending.pop(0)
            if name in resources:continue
            safe_name(name);path=(root/Path(*PurePosixPath(name).parts)).resolve(strict=True)
            need(path.is_relative_to(root) and path.is_file() and path.stat().st_size<=32*1024*1024,'HTML resource escapes root/missing/oversized')
            data=path.read_bytes();resources[name]=data;source_files.append(file_record(path))
            if Path(name).suffix.lower() in ('.html','.xhtml'):
                node=parse_xml(data);documents.append(name)
                for item in node.iter():
                    for attr in ('href','src'):
                        if item.get(attr):
                            target=local_resource(name,item.get(attr))
                            if target and target not in resources:pending.append(target)
            elif Path(name).suffix.lower()=='.css':
                text=data.decode('utf-8')
                need('@import' not in text.lower(),'CSS imports unsupported; supply a self-contained stylesheet')
                for uri in re.findall(r'url\(\s*[\'\"]?([^\'\")\s]+)',text):
                    target=local_resource(name,uri)
                    if target and target not in resources:pending.append(target)
            need(len(resources)+len(pending)<=2000 and sum(map(len,resources.values()))<=LIMIT,'HTML resource limits exceeded')
    need(1<=len(documents)<=100,'Reader harness requires 1..100 documents')
    styles=[(name,data.decode('utf-8')) for name,data in resources.items() if Path(name).suffix.lower()=='.css']
    for doc in documents:
        node=parse_xml(resources[doc]);need(all(n.tag.split('}')[-1].lower() not in ('script','iframe','object','embed','form','base') and not any(k.lower().startswith('on') for k in n.attrib) for n in node.iter()),'Active content unsupported by local reader harness')
        for item in node.iter():
            tag=item.tag.split('}')[-1].lower()
            if tag=='link' and 'stylesheet' in item.get('rel','').lower().split():
                dependency=local_resource(doc,item.get('href',''))
                need(dependency is not None and dependency in resources,'External/missing stylesheet requires another explicitly authorized reader route')
            if tag=='style':styles.append((doc,item.text or ''))
            if item.get('style'):styles.append((doc,item.get('style')))
    for name,text in styles:
        need('@import' not in text.lower(),'CSS imports unsupported by local reader harness')
        for uri in re.findall(r'url\(\s*[\'\"]?([^\'\")\s]+)',text):
            dependency=local_resource(name,uri)
            need(dependency is not None and dependency in resources,'External/missing CSS resource cannot establish current reading appearance')
    return resources,documents,source_files

def browser_check(artifact,kind,settings,target):
    keys=('node','playwright_module','browser','conditions','timeout_seconds')
    reading.keys(settings,(),keys)
    required=('node','playwright_module','browser')
    if not all(settings.get(k) and Path(settings[k]).is_file() for k in required):
        return {'state':'unavailable','reason':'Explicit existing Node, playwright-core entry module and Chromium executable required; no installation attempted'}
    tools={k:file_record(settings[k]) for k in required}
    conditions=settings.get('conditions',[{'width':360,'height':800,'text_scale':1},{'width':768,'height':900,'text_scale':1.5}])
    need(isinstance(conditions,list) and 1<=len(conditions)<=4,'Use 1..4 reader conditions')
    for c in conditions:
        reading.keys(c,('width','height','text_scale'))
        need(type(c['width']) is int and 240<=c['width']<=1600 and type(c['height']) is int and 320<=c['height']<=1200,'Unsupported viewport')
        need(type(c['text_scale']) in (int,float) and 0.5<=c['text_scale']<=3,'Unsupported text scale')
    timeout=settings.get('timeout_seconds',180);need(type(timeout) is int and 5<=timeout<=600,'Reader timeout must be 5..600 seconds')
    resources,documents,sources=reading_snapshot(artifact,kind)
    need(len(documents)*len(conditions)<=200,'Reader screenshot bound exceeded')
    probe=Path(__file__).with_name('reader_probe.mjs');helper=file_record(probe)
    with tempfile.TemporaryDirectory(prefix='book-reader-') as tmp:
        work=Path(tmp);root=work/'book';root.mkdir();outputs=work/'results';outputs.mkdir()
        for name,data in resources.items():
            path=root/Path(*PurePosixPath(name).parts);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        cfg={'root':str(root),'output':str(outputs),'resources':list(resources),'documents':documents,'conditions':conditions,'timeout_seconds':timeout,**{k:settings[k] for k in required if k!='node'}}
        config=work/'probe.json';config.write_bytes(reading.encoded(cfg))
        command=[settings['node'],str(probe),str(config)]
        try:
            proc=subprocess.run(command,cwd=work,capture_output=True,timeout=timeout+15,check=False)
            (target/'browser-stdout.txt').write_bytes(proc.stdout[:1024*1024]);(target/'browser-stderr.txt').write_bytes(proc.stderr[:1024*1024])
            if proc.returncode or not (outputs/'reader-probe.json').is_file():
                return {'state':'blocked','reason':'Actual reader launch/execution failed; inspect retained stderr','returncode':proc.returncode,'tools':tools,'helper':helper}
            result=load(outputs/'reader-probe.json')
            need(result.get('adapter')=='v11-reader-probe' and result.get('state') in ('passed','failed'),'Malformed reader execution report')
            need(sum(c.get('kind')=='reflow' for c in result['checks'])==len(documents)*len(conditions),'Incomplete reader condition coverage')
            for record in result['screenshots']:
                safe_name(record['path']);need('/' not in record['path'],'Unsafe screenshot path')
                source=outputs/record['path'];dest=target/record['path'];shutil.copyfile(source,dest);record.update(sha256=sha(dest),bytes=dest.stat().st_size)
            (target/'reader-probe.json').write_bytes(reading.encoded(result))
        except subprocess.TimeoutExpired:
            return {'state':'blocked','reason':'Actual reader execution timed out; no completed coverage claimed','tools':tools,'helper':helper}
    need(all(sha(settings[k])==v['sha256'] for k,v in tools.items()) and sha(probe)==helper['sha256'],'Reader tool changed during execution')
    return {'state':result['state'],'tools':tools,'helper':helper,'browser_version':result['browser_version'],'playwright_version':result['playwright_version'],
        'documents':documents,'conditions':conditions,'report':'reader-probe.json','screenshots':result['screenshots'],
        'source_resources':sources,'snapshot_resources':[{'path':n,'sha256':reading.sha(b),'bytes':len(b)} for n,b in sorted(resources.items())],
        'limits':result['limitations']}

def pdf_check(artifact,settings,target):
    from pypdf import PdfReader
    reading.keys(settings,(),('expected_size_pt','tolerance_pt','require_embedded_fonts','require_text','pdfinfo','renderer','pages','dpi'))
    reader=PdfReader(artifact,strict=True);need(not reader.is_encrypted,'Encrypted PDF unsupported')
    need(1<=len(reader.pages)<=5000,'PDF page count outside 1..5000')
    size=settings.get('expected_size_pt');tol=settings.get('tolerance_pt',0.5)
    need(type(tol) in (int,float) and 0<=tol<=5,'PDF size tolerance outside 0..5pt')
    need(size is None or isinstance(size,list) and len(size)==2 and all(type(x) in (int,float) and 72<=x<=3600 for x in size),'Invalid expected PDF size')
    for field in ('require_embedded_fonts','require_text'):need(type(settings.get(field,True)) is bool,'PDF requirement must be boolean')
    checks=[];fonts=[]
    def inspect_font(ref,where):
        f=ref.get_object();sub=f.get('/Subtype');descriptor=f.get('/FontDescriptor')
        if sub=='/Type0':
            children=f.get('/DescendantFonts',[]);need(children,'Type0 missing descendant fonts')
            for child in children:inspect_font(child,where)
            return
        desc=descriptor.get_object() if descriptor else {}
        embedded=any(desc.get(k) and len(desc[k].get_object().get_data())>0 for k in ('/FontFile','/FontFile2','/FontFile3'))
        fonts.append({'location':where,'base_font':str(f.get('/BaseFont','')),'subtype':str(sub),'embedded':embedded})
        if settings.get('require_embedded_fonts',True):checks.append({'check':'embedded-font','location':where,'passed':embedded})
    def resources(obj,where,seen):
        obj=obj.get_object();identity=id(obj)
        if identity in seen:return
        seen.add(identity);need(len(seen)<=1000,'PDF resource recursion bound exceeded')
        for name,ref in obj.get('/Font',{}).items():inspect_font(ref,where+':'+str(name))
        for name,ref in obj.get('/XObject',{}).items():
            child=ref.get_object()
            if child.get('/Subtype')=='/Form' and child.get('/Resources'):resources(child['/Resources'],where+':'+str(name),seen)
    for n,page in enumerate(reader.pages,1):
        actual=[float(page.mediabox.width),float(page.mediabox.height)]
        checks.append({'check':'page-geometry','page':n,'size_pt':actual,'passed':all(0<x<=3600 for x in actual) and (size is None or all(abs(a-b)<=tol for a,b in zip(actual,size)))})
        crop=list(map(float,page.cropbox));media=list(map(float,page.mediabox))
        checks.append({'check':'crop-contained','page':n,'passed':crop[0]>=media[0] and crop[1]>=media[1] and crop[2]<=media[2] and crop[3]<=media[3] and crop[2]>crop[0] and crop[3]>crop[1]})
        if settings.get('require_text',True):checks.append({'check':'selectable-text-present','page':n,'passed':bool((page.extract_text() or '').strip())})
        if page.get('/Resources'):resources(page['/Resources'],'page:'+str(n),set())
    external={'state':'unavailable','reason':'No existing pdfinfo executable selected'}
    if settings.get('pdfinfo') and Path(settings['pdfinfo']).is_file():
        tool=file_record(settings['pdfinfo'])
        with tempfile.TemporaryDirectory(prefix='book-pdfinfo-') as tmp:
            staged=Path(tmp)/'document.pdf';shutil.copyfile(artifact,staged);need(sha(staged)==sha(artifact),'Staged PDF differs')
            version=subprocess.run([settings['pdfinfo'],'-v'],capture_output=True,timeout=15)
            proc=subprocess.run([settings['pdfinfo'],'-box','document.pdf'],cwd=tmp,capture_output=True,timeout=60)
            (target/'pdfinfo.txt').write_bytes(proc.stdout);(target/'pdfinfo-stderr.txt').write_bytes(proc.stderr)
        need(sha(settings['pdfinfo'])==tool['sha256'],'PDF tool changed')
        output=proc.stdout.decode(errors='replace');match=re.search(r'^Pages:\s+(\d+)\s*$',output,re.M)
        passed=proc.returncode==0 and version.returncode==0 and bool(match) and int(match[1])==len(reader.pages)
        external={'state':'passed' if passed else 'failed','tool':tool,'version':(version.stdout+version.stderr).decode(errors='replace').strip(),'returncode':proc.returncode,'report':'pdfinfo.txt','coverage':'Actual Poppler parse/metadata/page-box report; not a PDF/X or printer conformance validator'}
        checks.append({'check':'independent-pdfinfo-parse','passed':passed})
    rendered={'state':'unavailable','reason':'No existing pdftoppm renderer selected'}
    if settings.get('renderer') and Path(settings['renderer']).is_file():
        import render_review
        pages=settings.get('pages',[1]);dpi=settings.get('dpi',72)
        need(isinstance(pages,list) and 1<=len(pages)<=200 and len(set(pages))==len(pages) and all(type(p) is int and 1<=p<=len(reader.pages) for p in pages),'Invalid selected render pages')
        need(type(dpi) is int and 36<=dpi<=150,'Unsupported DPI')
        with tempfile.TemporaryDirectory(prefix='book-proof-') as tmp:
            root=Path(tmp);shutil.copyfile(artifact,root/'document.pdf');(root/'render.json').write_bytes(reading.encoded({'schema_version':1,'pdf':'document.pdf','renderer':settings['renderer'],'pages':pages,'dpi':dpi}))
            folder=target/'pdf-previews';manifest=render_review.render_review(root/'render.json',folder)
        # Source is the real persistent release; no dependency on deleted staging.
        manifest['pdf_path']=str(artifact);(folder/'manifest.json').write_bytes(reading.encoded(manifest));render_review.validate_review(folder/'manifest.json')
        rendered={'state':'rendered-review-pending','pages':pages,'manifest':'pdf-previews/manifest.json','limits':'Actual images created; no visual or physical acceptance inferred'}
    return {'state':'passed' if all(c['passed'] for c in checks) else 'failed','page_count':len(reader.pages),'checks':checks,'fonts':fonts,'independent_parse':external,'rendered':rendered,
        'limits':'Selected local geometry/font/text/parse checks only. Color management, ink limits, bleed policy, PDF/X, complete glyph correctness, printer acceptance and physical proof remain unassessed unless separately evidenced.'}

def observations_check(path,artifact):
    if path is None:return {'state':'unrun','checks':[],'limits':'No reader/assistive/physical observations supplied'}
    record=load(path);reading.keys(record,('schema_version','artifact_sha256','checks'))
    need(record['schema_version']==1 and record['artifact_sha256']==sha(artifact),'Observation record is stale or unsupported')
    need(isinstance(record['checks'],list) and len(record['checks'])<=200,'Invalid observation count')
    result=[];identities=set()
    for item in record['checks']:
        reading.keys(item,('id','method','environment','coverage','observation','status','limitations'),('attachments',))
        for field in ('id','environment','coverage','observation','limitations'):reading.string(item[field],field)
        need(item['id'] not in identities,'Duplicate observation ID');identities.add(item['id'])
        need(item['method'] in ('human-reader','assistive-technology','physical-proof','destination-validator'),'Unsupported observation method')
        need(item['status'] in ('passed','failed','blocked','unrun','not-applicable'),'Invalid observation status')
        attachments=[]
        for attachment in item.get('attachments',[]):
            reading.keys(attachment,('path','sha256'));relative=safe_name(attachment['path']);p=(Path(path).resolve().parent/relative).resolve(strict=True)
            need(p.is_relative_to(Path(path).resolve().parent),'Attachment escapes record directory')
            actual=file_record(p);need(actual['sha256']==attachment['sha256'],'Observation attachment changed');attachments.append(actual)
        result.append(dict(item,verified_attachments=attachments))
    return {'state':'recorded','record':file_record(path),'checks':result,'limits':'Supplied observations bound to exact file; identities, attachments and claims are not proof that an independent human or physical test happened.'}

def verify(artifact,kind,settings,target,observations=None,previous=None):
    artifact=Path(artifact).resolve(strict=True);target=Path(target).resolve();identity=file_record(artifact)
    need(kind in ('html','epub','pdf'),'Unknown release kind');need(artifact.suffix.lower() in {'html':('.html','.xhtml'),'epub':('.epub',),'pdf':('.pdf',)}[kind],'Artifact extension differs from selected kind')
    need(not target.exists() and not artifact.is_relative_to(target),'Output must be new and cannot contain source')
    reading.keys(settings,(),('browser','pdf','required_checks'))
    required=settings.get('required_checks',['browser'] if kind in ('html','epub') else ['pdf-local']);need(isinstance(required,list) and len(required)==len(set(required)) and all(x in ('browser','pdf-local','pdf-independent','pdf-render','human-reader','assistive-technology','physical-proof','destination-validator') for x in required),'Invalid required check categories')
    obs=observations_check(observations,artifact)
    previous_record=load(previous) if previous else None
    if previous_record:need(previous_record.get('adapter')=='verify-release','Unsupported previous verification report')
    target.mkdir(parents=True)
    report={'schema_version':1,'adapter':'verify-release','version':VERSION,'artifact':identity,'kind':kind,'settings':settings,'observations':obs,
            'previous':{'report':file_record(previous),'same_artifact':previous_record['artifact']['sha256']==identity['sha256'],'reuse':'No prior observation automatically copied'} if previous_record else None}
    try:
        if kind in ('html','epub'):report['browser']=browser_check(artifact,kind,settings.get('browser',{}),target)
        else:report['pdf']=pdf_check(artifact,settings.get('pdf',{}),target)
    except Exception as exc:report['execution_error']=type(exc).__name__+': '+str(exc)
    states={}
    if 'browser' in report:states['browser']=report['browser']['state']
    if 'pdf' in report:
        states.update({'pdf-local':report['pdf']['state'],'pdf-independent':report['pdf']['independent_parse']['state'],'pdf-render':'passed' if report['pdf']['rendered']['state']=='rendered-review-pending' else report['pdf']['rendered']['state']})
    for method in ('human-reader','assistive-technology','physical-proof','destination-validator'):
        items=[c for c in obs['checks'] if c['method']==method]
        states[method]='passed' if items and all(c['status']=='passed' for c in items) else 'failed' if any(c['status']=='failed' for c in items) else 'unrun'
    report['check_states']=states;report['required_pending']=[k for k in required if states.get(k)!='passed']
    failures=report.get('execution_error') or any(v=='failed' for v in states.values())
    report['state']='failed' if failures else 'pending' if report['required_pending'] else 'completed-scoped-checks'
    report['acceptance']='No automatic reader, physical proof, printer or publication approval'
    need(sha(artifact)==identity['sha256'],'Artifact changed during verification')
    if observations:need(sha(observations)==obs['record']['sha256'],'Observation record changed during verification')
    browser=report.get('browser',{})
    for source in browser.get('source_resources',[]):need(sha(source['path'])==source['sha256'],'HTML resource changed during verification')
    report['evidence']=[{'path':p.relative_to(target).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(target.rglob('*')) if p.is_file()]
    (target/'verification.json').write_bytes(reading.encoded(report));return report

def recheck(path,artifact=None):
    path=Path(path).resolve(strict=True);report=load(path);need(report.get('adapter')=='verify-release' and report.get('schema_version')==1,'Unsupported verification evidence')
    actual=Path(artifact or report['artifact']['path']).resolve(strict=True);need(sha(actual)==report['artifact']['sha256'],'Verification stale: exact artifact changed')
    for e in report['evidence']:
        name=safe_name(e['path']);p=(path.parent/name).resolve(strict=True)
        need(p.is_relative_to(path.parent) and sha(p)==e['sha256'],'Verification evidence missing/changed')
    if report['kind']=='html':
        for src in report.get('browser',{}).get('source_resources',[]):
            original=Path(report['artifact']['path']).parent;relative=Path(src['path']).relative_to(original);p=(actual.parent/relative).resolve(strict=True)
            need(p.is_relative_to(actual.parent) and sha(p)==src['sha256'],'HTML resource verification stale')
    for c in report.get('observations',{}).get('checks',[]):
        for a in c.get('verified_attachments',[]):need(sha(a['path'])==a['sha256'],'Observation attachment missing/changed')
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifact',type=Path);parser.add_argument('--kind',choices=('html','epub','pdf'));parser.add_argument('--settings',type=Path);parser.add_argument('--output-dir',type=Path);parser.add_argument('--observations',type=Path);parser.add_argument('--previous-report',type=Path);parser.add_argument('--recheck',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.recheck:report=recheck(args.recheck,args.artifact);print(json.dumps({'state':'evidence-current','original_state':report['state']},indent=2));return 0
        need(args.artifact and args.kind and args.output_dir,'artifact,kind,output-dir required')
        settings=load(args.settings) if args.settings else {};report=verify(args.artifact,args.kind,settings,args.output_dir,args.observations,args.previous_report)
        print(json.dumps({'state':report['state'],'required_pending':report['required_pending'],'report':str(args.output_dir/'verification.json')},indent=2));return 2 if report['state']=='failed' else 0
    except Exception as exc:
        print(json.dumps({'state':'refused','error':str(exc)},indent=2));return 2
if __name__=='__main__':raise SystemExit(main())
