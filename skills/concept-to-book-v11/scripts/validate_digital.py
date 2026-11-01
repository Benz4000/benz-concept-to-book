"""Optional real EPUBCheck execution and separately declared reader-check evidence."""
import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
import run_project as common

need, sha, encoded, strict_json = common.need, common.sha, common.encoded, common.strict_json
AREAS = {'navigation','reflow','image-descriptions','coverage'}


def structured_report(path,epub,version,working_directory=None):
    """Reject malformed/wrong-target results; verify reported archive entry checksums."""
    need(Path(path).stat().st_size<=32*1024*1024,'Validator report exceeds bound')
    report=strict_json(path)
    need(isinstance(report,dict) and isinstance(report.get('checker'),dict) and isinstance(report.get('messages'),list) and isinstance(report.get('items'),list),'Malformed EPUBCheck JSON report')
    checker=report['checker']
    reported=Path(checker.get('path',''))
    if not reported.is_absolute():
        reported=Path(working_directory or Path.cwd())/reported
    need(reported.resolve()==Path(epub).resolve() and checker.get('filename')==Path(epub).name,'EPUBCheck report targets a different EPUB')
    need(isinstance(checker.get('checkerVersion'),str) and checker['checkerVersion'] in version,'EPUBCheck report version mismatch')
    counts={key:checker.get(key) for key in ('nFatal','nError','nWarning','nUsage')}
    need(all(type(value) is int and value>=0 for value in counts.values()),'Malformed EPUBCheck severity counts')
    checked=[]
    with zipfile.ZipFile(epub) as archive:
        for item in report['items']:
            need(isinstance(item,dict),'Malformed EPUBCheck item')
            checksum=item.get('checkSum')
            if checksum:
                name=item.get('fileName')
                need(isinstance(name,str) and name in archive.namelist(),'EPUBCheck report references an unknown archive item')
                digest=sha(archive.read(name))
                # EPUBCheck 5.4.0 serializes each digest byte without a leading
                # zero nibble; preserve the external report and compare that
                # observed representation as well as conventional SHA-256 hex.
                unpadded=''.join(format(int(digest[i:i+2],16),'x') for i in range(0,64,2))
                need(checksum==digest or checker['checkerVersion']=='5.4.0' and checksum==unpadded,'EPUBCheck report item checksum mismatch')
                checked.append(name)
    need(checked,'EPUBCheck report has no verifiable item checksums')
    return dict(counts,verified_archive_items=sorted(set(checked)),clean=counts['nFatal']==0 and counts['nError']==0)


def capability(settings):
    need(isinstance(settings,dict) and set(settings) <= {'java','jar','timeout_seconds'}, 'Unknown EPUB validator settings')
    timeout = settings.get('timeout_seconds',120)
    need(type(timeout) is int and 1 <= timeout <= 300, 'Validator timeout must be 1..300 seconds')
    java = shutil.which(settings.get('java','java'))
    jar = Path(settings['jar']).resolve() if settings.get('jar') else None
    result = {'available':False,'java':str(Path(java).resolve()) if java else None,'java_sha256':None,'java_version':None,'jar':str(jar) if jar else None,'jar_sha256':None,'distribution_jars':{},'version':None,'reason':None}
    if not java or not jar or not jar.is_file():
        result['reason'] = 'EPUBCheck jar or Java unavailable; validator was not run'
        return result
    need(jar.suffix.lower() == '.jar' and jar.stat().st_size <= 100*1024*1024,'Invalid or oversized EPUBCheck jar')
    result['jar_sha256'] = sha(jar.read_bytes())
    result['java_sha256'] = sha(Path(java).read_bytes())
    libraries=sorted((jar.parent/'lib').glob('*.jar'))
    need(len(libraries)<=200 and sum(p.stat().st_size for p in libraries)<=200*1024*1024,'EPUBCheck distribution libraries exceed bound')
    for library in libraries:
        need(not library.is_symlink(),'Symlink validator library forbidden')
        result['distribution_jars'][library.relative_to(jar.parent).as_posix()]=sha(library.read_bytes())
    try:
        java_probe=subprocess.run([java,'-version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15,shell=False)
        result['java_version']=(java_probe.stdout+'\n'+java_probe.stderr).strip()[:10000]
        probe = subprocess.run([java,'-jar',str(jar),'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15,shell=False)
        result['version'] = (probe.stdout+'\n'+probe.stderr).strip()[:10000]
        result['available'] = probe.returncode == 0 and 'epubcheck' in result['version'].lower()
        if not result['available']:
            result['reason'] = 'EPUBCheck version probe failed'
    except (OSError,subprocess.SubprocessError) as exc:
        result['reason'] = type(exc).__name__+': '+str(exc)
    return result


def reader_evidence(record, digest):
    if record is None:
        return {'state':'unrun','checks':[],'missing_areas':sorted(AREAS),'limits':'No EPUB reader or accessibility inspection was supplied.'}
    need(isinstance(record,dict) and set(record) == {'schema_version','epub_sha256','checks'} and record['schema_version']==1,'Invalid reader-check schema')
    need(isinstance(record['checks'],list) and len(record['checks']) <= 10000,'Reader checks must be bounded list')
    checks=[]
    for item in record['checks']:
        need(isinstance(item,dict) and set(item)=={'area','method','viewer','environment','coverage','observation','status','limitations'},'Explicit reader-check fields required')
        need(item['area'] in AREAS and item['method'] in ('human-reader','assistive-technology','source-inspection'),'Invalid reader-check area/method')
        need(item['status'] in ('passed','failed','blocked','unrun','not-applicable'),'Invalid reader-check status')
        need(all(isinstance(item[k],str) and item[k].strip() for k in ('viewer','environment','coverage','observation','limitations')),'Explicit coverage, observation and limits required')
        checks.append(dict(item,evidence_binding='current-exact-epub' if record['epub_sha256']==digest else 'stale-epub-hash',assertion='supplied observation; not independently verified'))
    missing=sorted(AREAS-{c['area'] for c in checks})
    state='stale' if record['epub_sha256']!=digest else ('incomplete' if missing else 'recorded')
    return {'state':state,'record_epub_sha256':record['epub_sha256'],'checks':checks,'missing_areas':missing,'limits':'Reader assertions are separate from validator results and do not establish universal accessibility.'}


def validate(epub, output_dir, settings=None, reader_record=None):
    epub=Path(epub).resolve(strict=True)
    need(epub.is_file() and epub.suffix.lower()=='.epub','Explicit EPUB file required')
    blob=epub.read_bytes(); digest=sha(blob)
    target=Path(output_dir).resolve()
    need(not target.exists() and not epub.is_relative_to(target),'New output directory must not contain the EPUB input')
    settings=settings or {}
    tool=capability(settings)
    reader=reader_evidence(strict_json(reader_record) if reader_record else None,digest)
    target.mkdir(parents=True)
    automated={'state':'unavailable','exit_code':None,'command':None,'report':None}
    if tool['available']:
        report=target/'epubcheck-report.json'
        command=[tool['java'],'-jar',tool['jar'],str(epub),'--json',str(report)]
        automated['command']=command
        automated['working_directory']=str(epub.parent)
        try:
            process=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=settings.get('timeout_seconds',120),shell=False,cwd=epub.parent)
            (target/'validator-stdout.txt').write_text(process.stdout,encoding='utf-8')
            (target/'validator-stderr.txt').write_text(process.stderr,encoding='utf-8')
            automated.update(exit_code=process.returncode,state='passed' if process.returncode==0 and report.is_file() else 'failed')
            if report.is_file():
                automated['report']={'path':report.name,'sha256':sha(report.read_bytes())}
                try:
                    automated['structured_result']=structured_report(report,epub,tool['version'],epub.parent)
                    if not automated['structured_result']['clean']:
                        automated['state']='failed'
                except (ValueError,OSError,KeyError,TypeError,zipfile.BadZipFile) as exc:
                    automated.update(state='failed',reason='Unusable validator report: '+str(exc))
            if process.returncode==0 and not report.is_file():
                automated['reason']='Validator returned zero without requested report; no pass claimed'
        except subprocess.TimeoutExpired as exc:
            automated.update(state='blocked',reason='Validator timed out')
            (target/'validator-stdout.txt').write_bytes(exc.stdout or b'')
            (target/'validator-stderr.txt').write_bytes(exc.stderr or b'')
    need(sha(epub.read_bytes())==digest,'EPUB changed during validation')
    if tool['jar_sha256']:
        after=capability(settings)
        need(all(after[key]==tool[key] for key in ('java_sha256','java_version','jar_sha256','distribution_jars','version')),'Validator or Java changed during execution')
    result={'schema_version':1,'epub':{'absolute_path':str(epub),'sha256':digest,'bytes':len(blob)},'validator':tool,'automated_validation':automated,'reader_checks':reader,'accessibility_state':'not-established','limits':'EPUBCheck checks its documented package/content rules. A validator pass is not human reading, assistive-technology testing, accessibility certification or publisher acceptance.'}
    (target/'validation.json').write_bytes(encoded(result))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epub',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--settings',type=Path)
    parser.add_argument('--reader-record',type=Path)
    args=parser.parse_args(argv)
    try:
        print(encoded(validate(args.epub,args.output_dir,strict_json(args.settings) if args.settings else None,args.reader_record)).decode())
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'refused','error':str(exc)})); return 2

if __name__=='__main__':
    raise SystemExit(main())
