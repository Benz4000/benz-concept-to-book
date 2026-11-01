"""Report explicit source records and verify selected file bytes; never infer influence."""
import argparse
import json
import re
from pathlib import Path
import run_project as common

need, inside, sha, encoded, strict_json = common.need, common.inside, common.sha, common.encoded, common.strict_json

def report(input_root, record, output_root, output_dir):
    root = Path(input_root).resolve(strict=True)
    data = strict_json(inside(root,record))
    need(isinstance(data,dict) and set(data) == {'schema_version','sources'} and data['schema_version'] == 1, 'Invalid source-use schema')
    need(isinstance(data['sources'],list), 'sources must be list')
    rows, ids = [], set()
    for source in data['sources']:
        need(isinstance(source,dict) and set(source) == {'source_id','path','availability','sha256','read_record','interpretation','scoped_decision','destinations'}, 'Invalid source fields')
        sid = source['source_id']
        need(isinstance(sid,str) and sid and sid not in ids, 'Unique nonempty source_id required')
        ids.add(sid)
        need(source['availability'] in ('available','unavailable'), 'availability must be explicit')
        for key in ('interpretation','scoped_decision'):
            need(isinstance(source[key],str) and source[key].strip(), key+' must be explicit')
        read = source['read_record']
        need(isinstance(read,dict) and set(read) == {'status','scope','locator','start_byte','end_byte','excerpt_sha256'}, 'Invalid read_record')
        need(read['status'] in ('read','partial','not-read'), 'Invalid read status')
        need(all(isinstance(read[k],str) and read[k].strip() for k in ('scope','locator')), 'Read scope and locator required')
        source_status, excerpt_status = 'unavailable', 'unverified'
        for digest in [source['sha256'],read['excerpt_sha256']]:
            need(digest is None or isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest), 'Invalid SHA-256')
        if source['availability'] == 'available':
            need(source['sha256'] is not None, 'Available source requires expected hash')
            if read['status'] != 'not-read':
                need(type(read['start_byte']) is int and type(read['end_byte']) is int and 0 <= read['start_byte'] < read['end_byte'] and read['excerpt_sha256'] is not None, 'Claimed read excerpt requires valid byte range and expected hash')
            else:
                need(read['start_byte'] is None and read['end_byte'] is None and read['excerpt_sha256'] is None, 'not-read cannot claim excerpt')
        if source['availability'] == 'unavailable':
            need(source['path'] is None and source['sha256'] is None and read['start_byte'] is None and read['end_byte'] is None and read['excerpt_sha256'] is None, 'Unavailable source must not claim local path/hash/excerpt verification')
        else:
            path = inside(root,source['path'],False)
            if path.is_file():
                blob = path.read_bytes()
                source_status = 'verified-file-access' if sha(blob) == source['sha256'] else 'changed-source-hash'
                if read['status'] != 'not-read':
                    a,b = read['start_byte'],read['end_byte']
                    need(type(a) is int and type(b) is int and 0 <= a < b, 'Invalid selected excerpt byte range')
                    excerpt_status = 'verified-selected-excerpt' if b <= len(blob) and sha(blob[a:b]) == read['excerpt_sha256'] else 'stale-excerpt-hash'
                else:
                    need(read['start_byte'] is None and read['end_byte'] is None and read['excerpt_sha256'] is None, 'not-read cannot claim excerpt')
            else:
                source_status = 'missing-source-file'
        need(isinstance(source['destinations'],list), 'destinations must be list')
        destinations = []
        for destination in source['destinations']:
            need(isinstance(destination,dict) and set(destination) == {'path','sha256','locator','use'}, 'Invalid destination fields')
            need(isinstance(destination['sha256'],str) and re.fullmatch(r'[0-9a-f]{64}',destination['sha256']), 'Destination hash required')
            need(destination['use'] in ('citation','production-reference','declared-application'), 'Invalid destination use')
            need(isinstance(destination['locator'],str) and destination['locator'], 'Destination locator required')
            path = inside(root,destination['path'],False)
            status = 'missing-destination-file' if not path.is_file() else ('verified-destination-file' if sha(path.read_bytes()) == destination['sha256'] else 'changed-destination-hash')
            destinations.append(dict(destination,verification=status,source_provenance='stale-or-unavailable' if source_status != 'verified-file-access' or (read['status'] != 'not-read' and excerpt_status != 'verified-selected-excerpt') else 'current-byte-evidence'))
        rows.append(dict(source,source_verification=source_status,excerpt_verification=excerpt_status,destinations=destinations))
    out = Path(output_root).resolve(strict=True)
    need(out.is_dir() and not out.is_relative_to(root) and not root.is_relative_to(out), 'Output root must be external and disjoint')
    need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',output_dir) and output_dir.lower() not in {'con','prn','aux','nul'} | {f'{p}{i}' for p in ('com','lpt') for i in range(1,10)}, 'Safe single output directory required')
    target = out/output_dir
    need(not target.exists(), 'Output exists; overwrite forbidden')
    result = {'schema_version':1,'record_sha256':sha(inside(root,record).read_bytes()),'evidence_policy':'Supplied read records and declared application are user assertions. Verified file access and selected excerpt byte hashes establish byte correspondence only; they cannot prove understanding, complete reading, influence, citation adequacy or successful application. Unavailable sources require no private vault. No source is inferred from file existence.','sources':rows}
    md = ['# Explicit source-to-output coverage', '',result['evidence_policy'],'']
    for source in rows:
        md += ['## '+source['source_id'],'','Source: '+str(source['path'] or 'unavailable'), '','Read record: '+source['read_record']['status']+'; '+source['read_record']['scope']+'; '+source['read_record']['locator'],'','Verification: '+source['source_verification']+'; '+source['excerpt_verification'],'','Interpretation (declared): '+source['interpretation'],'','Scoped decision (declared): '+source['scoped_decision'],'']
        for d in source['destinations']:
            md += ['- '+d['use']+': '+d['path']+' @ '+d['locator']+'; '+d['verification']+'; '+d['source_provenance']]
        md.append('')
    target.mkdir()
    (target/'source-coverage.json').write_bytes(encoded(result))
    (target/'source-coverage.md').write_text('\n'.join(md),encoding='utf-8')
    return {'output_directory':str(target),'sources':len(rows),'report_sha256':sha((target/'source-coverage.json').read_bytes())}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root',required=True,type=Path)
    p.add_argument('--record',required=True)
    p.add_argument('--output-root',required=True,type=Path)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args(argv)
    try:
        print(encoded(report(a.input_root,a.record,a.output_root,a.output_dir)).decode('utf-8'))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'refused','error':str(exc)}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
