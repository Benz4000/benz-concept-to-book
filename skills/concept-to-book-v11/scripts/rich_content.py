"""V11 bounded block extensions shared by import, export and audit."""
import html

def leaves(block):
    if block.get('type') == 'table':
        return [p for row in block['rows'] for cell in row for p in cell]
    if block.get('paragraphs'):
        return block['paragraphs']
    return [block] if 'text' in block else []

def text(block):
    return '\n'.join(p['text'] for p in leaves(block))

def anchor_map(sections, need):
    anchors, refs = {}, []
    for section in sections:
        for block in [{'anchors':section.get('anchors', [])}] + section['blocks']:
            for item in [block] + ([p for p in leaves(block) if p is not block]):
                for aid in item.get('anchors', []):
                    need(aid not in anchors, 'Duplicate internal anchor: '+aid)
                    anchors[aid] = section['id']
                for run in item.get('runs', []):
                    if 'target_id' in run: refs.append(run['target_id'])
        for run in section.get('title_runs', []):
            if 'target_id' in run: refs.append(run['target_id'])
    need(all(a in anchors for a in refs), 'Missing internal cross-reference target')
    return anchors

def validate_anchors(block, need, identifier):
    value=block.get('anchors', [])
    need(isinstance(value,list) and len(value)<=20 and len(set(value))==len(value), 'Invalid/duplicate block anchors')
    for aid in value:
        identifier(aid)
        need(aid.startswith('bm-'), 'Internal anchors must start bm-')

def validate_block(block, need, keys, string, identifier, inline):
    if block['type']=='table':
        keys(block, ('type','rows','header_rows'), ('anchors',))
        need(type(block['header_rows']) is int and block['header_rows'] in (0,1), 'table.header_rows must be 0 or 1')
        rows=block['rows']
        need(isinstance(rows,list) and 1<=len(rows)<=100, 'Table requires 1..100 rows')
        n=len(rows[0]) if isinstance(rows[0],list) else 0
        need(1<=n<=8 and all(isinstance(r,list) and len(r)==n for r in rows), 'Tables must be rectangular with 1..8 columns')
        need(block['header_rows']<len(rows), 'Header requires at least one data row')
        for row in rows:
            for cell in row:
                need(isinstance(cell,list) and 1<=len(cell)<=20, 'Each cell requires 1..20 paragraphs')
                for p in cell:
                    keys(p,('text',),('runs','anchors'))
                    string(p['text'],'table paragraph')
                    inline(p,need,keys,string)
                    validate_anchors(p,need,identifier)
    else:
        keys(block,('type','id','text','paragraphs'),('runs','anchors'))
        ps=block['paragraphs']
        need(isinstance(ps,list) and 2<=len(ps)<=100, 'Extended endnote requires 2..100 paragraphs')
        for p in ps:
            keys(p,('text',),('runs',))
            string(p['text'],'note paragraph');inline(p,need,keys,string)
        need(block['text']=='\n'.join(p['text'] for p in ps), 'Endnote paragraphs differ from text')
        need('runs' not in block, 'Multi-paragraph endnote cannot also carry flat runs')
    validate_anchors(block,need,identifier)

def anchors_markup(block):
    return ''.join('<span id="'+html.escape(a,quote=True)+'"></span>' for a in block.get('anchors',[]))

def table_markup(block, render):
    rows=[]
    for i,row in enumerate(block['rows']):
        tag='th' if i<block['header_rows'] else 'td'
        scope=' scope="col"' if tag=='th' else ''
        rows.append('<tr>'+''.join('<'+tag+scope+'>'+''.join('<p>'+anchors_markup(p)+render(p)+'</p>' for p in cell)+'</'+tag+'>' for cell in row)+'</tr>')
    h=block['header_rows']
    return anchors_markup(block)+'<table>'+('<thead>'+''.join(rows[:h])+'</thead>' if h else '')+'<tbody>'+''.join(rows[h:])+'</tbody></table>'
