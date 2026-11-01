"""Opt-in V11 DOCX: rectangular tables, collected multi-paragraph notes, REF links.

Reuses the strict importer for each paragraph and the complete package scan.
No source part is edited on disk. Unsupported structures still fail explicitly.
"""
import copy,io,re,zipfile
import xml.etree.ElementTree as ET
import rich_content as rich

def parse(data, base):
    W=base.W; q=lambda n:'{'+W+'}'+n
    R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    PR='http://schemas.openxmlformats.org/package/2006/relationships'
    need=base.need
    def xml(blob):
        need(b'<!DOCTYPE' not in blob.upper() and b'<!ENTITY' not in blob.upper(),'DTD/entities forbidden')
        return ET.fromstring(blob)
    # First enforce the existing ZIP/package constraints on the complete file.
    _,scan_issues,counts=base.docx(_without_extended_content(data,base))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        blobs={i.filename:archive.read(i) for i in archive.infolist() if not i.is_dir()}
    root=xml(blobs['word/document.xml']);body=root.find(q('body'))
    need(body is not None,'DOCX body absent')
    for node in root.iter():
        need(node.tag==q('t') or not (node.text and node.text.strip()),'Unexpected mixed XML text in extended document')
        need(not (node.tail and node.tail.strip()),'Unexpected XML tail text in extended document')
    units,issues=[],list(scan_issues)
    bookmarks={};bookmark_ids=set()
    for i,node in enumerate(root.iter(q('bookmarkStart')),1):
        name=node.get(q('name'));bid=node.get(q('id'))
        need(name and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',name) and bid and name not in bookmarks and bid not in bookmark_ids,'Invalid/duplicate bookmark')
        need(set(node.attrib)=={q('id'),q('name')} and not len(node),'Unsupported bookmark shape')
        bookmarks[name]='bm-'+str(i);bookmark_ids.add(bid)
    base_rels=xml(blobs.get('word/_rels/document.xml.rels',b'<Relationships/>'))
    def paragraph(original,loc,note=False):
        p=copy.deepcopy(original);anchors=[]
        starts=[n for n in p if n.tag==q('bookmarkStart')];ends=[n for n in p if n.tag==q('bookmarkEnd')]
        if starts or ends:
            need(not note and len(starts)==len(ends) and {n.get(q('id')) for n in starts}=={n.get(q('id')) for n in ends},'Only paragraph-contained bookmarks are supported: '+loc)
            content=[n for n in p if n.tag!=q('pPr')]
            need(all(n.tag==q('bookmarkStart') for n in content[:len(starts)]) and all(n.tag==q('bookmarkEnd') for n in content[len(content)-len(ends):]),'Bookmark must cover the entire paragraph: '+loc)
            for n in starts:
                anchors.append(bookmarks[n.get(q('name'))]);p.remove(n)
            for n in ends:
                need(set(n.attrib)=={q('id')} and not len(n),'Unsupported bookmark end');p.remove(n)
        rels=copy.deepcopy(base_rels);targets={}
        for child in list(p):
            need(not (note and child.tag==q("hyperlink") and q("anchor") not in child.attrib), "External hyperlinks in note parts require an unsupported note-specific relationship adapter: "+loc)
            target=None
            if child.tag==q('fldSimple'):
                instruction=child.get(q('instr'),'').strip()
                match=re.fullmatch(r'REF\s+([A-Za-z_][A-Za-z0-9_]{0,79})(?:\s+\\h)?',instruction)
                need(match is not None and set(child.attrib)=={q('instr')} and len(child) and all(c.tag==q('r') for c in child),'Only cached simple REF fields are supported: '+loc)
                target=match[1]
            elif child.tag==q('hyperlink') and q('anchor') in child.attrib:
                need(set(child.attrib)=={q('anchor')} and len(child) and all(c.tag==q('r') for c in child),'Unsupported internal hyperlink: '+loc)
                target=child.get(q('anchor'))
            if target is not None:
                need(target in bookmarks,'Missing bookmark target: '+str(target))
                rid='v11-'+str(len(targets)+1);uri='https://v11-crossref.invalid/'+bookmarks[target]
                targets[uri]=bookmarks[target]
                ET.SubElement(rels,'{'+PR+'}Relationship',{'Id':rid,'Type':R+'/hyperlink','TargetMode':'External','Target':uri})
                child.tag=q('hyperlink');child.attrib.clear();child.set('{'+R+'}id',rid)
        if note:
            for prop in p.findall(q('pPr')+'/'+q('pStyle')):
                if prop.get(q('val')) in ('FootnoteText','EndnoteText'):prop.set(q('val'),'Normal')
            for run in p.findall(q('r')):
                for node in list(run):
                    if node.tag in (q('footnoteRef'),q('endnoteRef')):
                        need(not node.attrib and not len(node),'Unsupported note marker');run.remove(node)
                    elif node.tag==q('tab') and not node.attrib and not len(node):node.tag=q('t');node.text='\t'
        doc=ET.Element(q('document'));ET.SubElement(doc,q('body')).append(p)
        mini=io.BytesIO()
        with zipfile.ZipFile(mini,'w') as z:
            z.writestr('word/document.xml',ET.tostring(doc));z.writestr('word/_rels/document.xml.rels',ET.tostring(rels))
            z.writestr('[Content_Types].xml',b'<Types/>');z.writestr('_rels/.rels',b'<Relationships/>')
        parsed,problems,_=base.docx(mini.getvalue())
        issues.extend({'feature':p['feature'],'location':loc+':'+p['location']} for p in problems)
        need(len(parsed)<=1,'Unexpected paragraph expansion')
        if not parsed:
            need(not anchors,'Empty bookmark paragraph unsupported');return None
        result=parsed[0];result['locator']=loc
        if anchors:result['anchors']=anchors
        for run in result.get('runs',[]):
            if run.get('href') in targets:run['target_id']=targets[run.pop('href')]
        return result
    for idx,child in enumerate(body,1):
        loc='word/document.xml:body-child:'+str(idx)
        if child.tag==q('p'):
            p=paragraph(child,loc)
            if p:units.append(p)
        elif child.tag==q('tbl'):
            need(not child.attrib,'Table attributes unsupported: '+loc)
            rows=[];header=0
            for prop in child:
                if prop.tag==q('tblPr'):
                    need(all(n.tag in (q('tblW'),q('tblLayout')) and not len(n) for n in prop),'Unsupported table property: '+loc)
                elif prop.tag==q('tblGrid'):
                    need(all(n.tag==q('gridCol') and not len(n) for n in prop),'Unsupported table grid: '+loc)
                elif prop.tag==q('tr'):
                    need(not prop.attrib,'Row attributes unsupported: '+loc)
                    row=[]
                    for cell in prop:
                        if cell.tag==q('trPr'):
                            need(len(rows)==0 and len(cell)==1 and cell[0].tag==q('tblHeader') and cell[0].get(q('val'),'true') in ('true','1','on'),'Only first-row header property supported')
                            header=1;continue
                        need(cell.tag==q('tc'),'Unsupported row element: '+loc)
                        need(not cell.attrib,'Cell attributes unsupported: '+loc)
                        ps=[]
                        for node in cell:
                            if node.tag==q('tcPr'):
                                need(all(n.tag==q('tcW') and not len(n) for n in node),'Merged/styled cells unsupported: '+loc);continue
                            need(node.tag==q('p'),'Nested table/content unsupported: '+loc)
                            item=paragraph(node,loc+':row:'+str(len(rows)+1)+':cell:'+str(len(row)+1)+':paragraph:'+str(len(ps)+1))
                            need(item and item['type']=='paragraph','Table cells require nonempty ordinary paragraphs')
                            ps.append({k:v for k,v in item.items() if k not in ('type','locator')})
                        row.append(ps)
                    rows.append(row)
                else:need(False,'Unsupported table child: '+loc)
            unit={'type':'table','rows':rows,'header_rows':header,'locator':loc};unit['text']=rich.text(unit);units.append(unit)
        elif child.tag!=q('sectPr'):need(False,'Unsupported body element: '+loc)
    notes=[]
    for part,tag,prefix in (('word/footnotes.xml','footnote','fn-'),('word/endnotes.xml','endnote','en-')):
        if part not in blobs:continue
        nr=xml(blobs[part]);need(nr.tag==q(tag+'s'),'Unexpected note root')
        for node in nr.iter():
            need(node.tag==q('t') or not (node.text and node.text.strip()),'Unexpected mixed XML text in extended notes')
            need(not (node.tail and node.tail.strip()),'Unexpected XML tail text in extended notes')
        for n in nr:
            if n.get(q('type')) in ('separator','continuationSeparator'):continue # scan already checks textless separator shape
            nid=n.get(q('id'),'');need(n.tag==q(tag) and set(n.attrib)=={q('id')} and re.fullmatch(r'[0-9]{1,8}',nid),'Unsupported note identity')
            need(1<=len(n)<=100 and all(p.tag==q('p') for p in n),'Notes require 1..100 paragraphs')
            ps=[]
            for i,p in enumerate(n,1):
                item=paragraph(p,part+':'+nid+':paragraph:'+str(i),True)
                need(item and item['type']=='paragraph','Note paragraph must be nonempty ordinary text')
                need(all('note_id' not in r for r in item.get('runs',[])),'Nested note reference unsupported')
                ps.append({k:v for k,v in item.items() if k not in ('type','locator')})
            stable=prefix+nid;label={'text':'['+stable+'] ','emphasis':False,'strong':False}
            ps[0]={'text':label['text']+ps[0]['text'],'runs':[label]+base.semantic.runs(ps[0])}
            item={'type':'endnote','id':stable,'text':'\n'.join(p['text'] for p in ps),'locator':part+':'+nid}
            if len(ps)>1:item['paragraphs']=ps
            else:item.update(ps[0])
            notes.append(item)
    if notes:
        units.append({'type':'heading','text':'Endnotes','level':1,'locator':'generated:endnotes-heading'});units.extend(notes)
    counts['extended_docx']=True
    counts['docx_paragraphs']=sum(1 for _ in root.iter(q('p')))
    counts['tables']=sum(1 for _ in root.iter(q('tbl')))
    counts['note_paragraphs']=sum(len(n.get('paragraphs',[n])) for n in notes)
    counts['normalization']='Tables retain row/cell/paragraph order, header role; equal-width PDF cells; whole-paragraph bookmark anchors; cached REF labels retained, no field recalculation; native notes collected, no page footnotes.'
    return units,issues,counts

def _without_extended_content(data,base):
    """Bounded package scan, retaining every other part and style for strict refusals."""
    W=base.W;q=lambda n:'{'+W+'}'+n
    # Apply ZIP limits before materializing any member.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info=z.infolist();base.need(len(info)<=1000,'DOCX exceeds member limit')
        base.need(sum(i.file_size for i in info)<=base.MAX_ZIP_TOTAL and all(i.file_size<=base.MAX_FILE for i in info),'DOCX expanded-size limit exceeded')
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as target:
            for i in info:
                blob=z.read(i)
                if i.filename in ('word/document.xml','word/footnotes.xml','word/endnotes.xml'):
                    base.need(b'<!DOCTYPE' not in blob.upper() and b'<!ENTITY' not in blob.upper(),'DTD/entities forbidden')
                    root=ET.fromstring(blob)
                    if i.filename=='word/document.xml':
                        body=root.find(q('body'));base.need(body is not None,'DOCX body absent')
                        for node in list(body):
                            if node.tag in (q('p'),q('tbl')):body.remove(node)
                        p=ET.Element(q('p'));ET.SubElement(ET.SubElement(p,q('r')),q('t')).text='Package scan';body.insert(0,p)
                    else:
                        for n in list(root):
                            if n.get(q('type')) not in ('separator','continuationSeparator'):root.remove(n)
                    blob=ET.tostring(root)
                target.writestr(i,blob)
    return out.getvalue()
