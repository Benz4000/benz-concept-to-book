"""Bounded optional local stages for the project runner; no network or publication."""
import importlib
import shutil
from pathlib import Path
import run_project as common

need, inside, sha, encoded, strict_json, inventory = common.need, common.inside, common.sha, common.encoded, common.strict_json, common.inventory
STAGES={'validate-digital','cover','render','source-report','review','package'}


def jobs(cfg,key):
    value=cfg.get(key,[])
    need(isinstance(value,list) and len(value)<=12,key+' must be bounded list')
    ids=[]
    for job in value:
        need(isinstance(job,dict) and isinstance(job.get('id'),str),'Explicit job id required')
        name=job['id']
        need(name and len(name)<=60 and all(c.isascii() and (c.isalnum() or c in '-_') for c in name),'Safe job id required')
        ids.append(name)
    need(len(ids)==len(set(ids)),'Duplicate '+key+' ids')
    return value


def target_dependency(target):
    need(target=='pdf' or isinstance(target,str) and target.startswith('cover:'),'Target must be pdf or cover:JOB_ID')
    return 'pdf' if target=='pdf' else 'cover'


def dependencies(cfg,base):
    deps=dict(base)
    deps['validate-digital']=['digital']
    deps['cover']=['pdf']
    deps['render']=list(dict.fromkeys(target_dependency(j['target']) for j in jobs(cfg,'renders')))
    deps['review']=list(dict.fromkeys(['render']+[target_dependency(j['target']) for j in jobs(cfg,'reviews')]))
    deps['source-report']=cfg.get('source_report',{}).get('stages',[])
    deps['package']=cfg.get('package',{}).get('stages',[])
    for stage in ('source-report','package'):
        need(isinstance(deps[stage],list) and stage not in deps[stage] and set(deps[stage])<=set(base)|STAGES,'Invalid '+stage+' dependencies')
    return deps


def selected_references(cfg,root):
    refs=[]
    def read(name):
        refs.append(name)
        need(name in cfg['selected_inputs'],'Every referenced extension file must be selected before reading: '+name)
        p=inside(root,name,False)
        return strict_json(p) if p.is_file() else None
    validation=cfg.get('validation',{})
    need(isinstance(validation,dict) and set(validation)<= {'validator','reader_checks'},'Unknown validation settings')
    if validation.get('reader_checks'): refs.append(validation['reader_checks'])
    for job in jobs(cfg,'covers'):
        need(set(job)=={'id','config'},'Cover job requires id/config')
        data=read(job['config'])
        if data:
            for name in [data['template']]+[x['path'] for x in data['fonts']+data['images']]:
                # Cover configs use paths relative to their own directory.
                refs.append((Path(job['config']).parent/name).as_posix())
    for job in jobs(cfg,'renders'):
        need(set(job)=={'id','target','config'},'Render job requires id/target/config')
        target_dependency(job['target'])
        data=read(job['config'])
        if data:
            need(set(data)<= {'schema_version','pdf','pages','dpi','renderer','dispositions','disposition_pdf_sha256'},'Runner render config has unsupported keys (prior packets belong in explicit review records)')
    render_ids={j['id'] for j in jobs(cfg,'renders')}
    for job in jobs(cfg,'reviews'):
        need(set(job)<= {'id','target','packets','dispositions'} and {'id','target','packets'}<=set(job),'Review job fields invalid')
        target_dependency(job['target'])
        need(isinstance(job['packets'],list) and job['packets'] and set(job['packets'])<=render_ids,'Review names explicit render packet ids')
        if job.get('dispositions'): refs.append(job['dispositions'])
    covers={j['id'] for j in jobs(cfg,'covers')}
    for job in jobs(cfg,'renders')+jobs(cfg,'reviews'):
        need(job['target']=='pdf' or job['target'].split(':',1)[1] in covers,'Unknown cover target')
    source=cfg.get('source_report')
    if source is not None:
        need(isinstance(source,dict) and set(source)=={'record','stages'},'source_report requires record/stages')
        data=read(source['record'])
        if data:
            for s in data['sources']:
                paths=([s['path']] if s['path'] else [])+[d['path'] for d in s['destinations']]
                for name in paths:
                    if name.startswith('inputs/'):
                        refs.append(name[len('inputs/'):])
                    else:
                        need(name.startswith('outputs/'),'Source report paths use explicit inputs/ or outputs/ namespace')
    package=cfg.get('package')
    if package is not None:
        need(isinstance(package,dict) and set(package)=={'stages','required_reviews'},'package requires stages/required_reviews')
        need(isinstance(package['required_reviews'],list) and set(package['required_reviews'])<={j['id'] for j in jobs(cfg,'reviews')},'Unknown required review job')
        need(not package['required_reviews'] or 'review' in package['stages'],'Required review must be included in package stages')
    need(set(refs)<=set(cfg['selected_inputs']),'Every referenced extension config, asset, reader record and source must be selected')
    return refs


def stage_settings(cfg,stage):
    return cfg.get({'validate-digital':'validation','cover':'covers','render':'renders','source-report':'source_report','review':'reviews','package':'package'}[stage])


def relevant_inputs(cfg,root,stage):
    names=[]
    settings=stage_settings(cfg,stage)
    if stage=='validate-digital':
        if (settings or {}).get('reader_checks'): names.append(settings['reader_checks'])
    elif stage=='cover':
        for job in jobs(cfg,'covers'):
            names.append(job['config']); data=strict_json(inside(root,job['config']))
            names += [(Path(job['config']).parent/name).as_posix() for name in [data['template']]+[x['path'] for x in data['fonts']+data['images']]]
    elif stage=='render': names += [j['config'] for j in jobs(cfg,'renders')]
    elif stage=='review': names += [j['dispositions'] for j in jobs(cfg,'reviews') if j.get('dispositions')]
    elif stage=='package': names += cfg['selected_inputs']
    elif stage=='source-report':
        names.append(settings['record']); record=strict_json(inside(root,settings['record']))
        for source in record['sources']:
            for name in ([source['path']] if source['path'] else [])+[d['path'] for d in source['destinations']]:
                if name.startswith('inputs/'): names.append(name[7:])
    return sorted(set(names))


def tools(cfg,stage,root=None):
    if stage=='validate-digital':
        from validate_digital import capability
        return {'epubcheck':capability((cfg.get('validation') or {}).get('validator',{}))}
    if stage=='render':
        import subprocess
        records=[]
        for job in jobs(cfg,'renders'):
            settings=strict_json(inside(root,job['config'])) if root else {}
            executable=shutil.which(settings.get('renderer','pdftoppm'))
            record={'id':job['id'],'available':bool(executable),'path':executable}
            if executable:
                probe=subprocess.run([executable,'-v'],capture_output=True,timeout=15,shell=False)
                record.update(sha256=sha(Path(executable).read_bytes()),version=(probe.stdout+probe.stderr).decode(errors='replace').strip(),probe_exit_code=probe.returncode)
            records.append(record)
        return {'render_jobs':records}
    return {}


def pdf_target(run,target):
    if target=='pdf':
        candidates=list((run/'pdf').glob('*.pdf'))
        need(len(candidates)==1,'Exactly one built interior PDF required')
        return candidates[0]
    return run/'cover'/target.split(':',1)[1]/'cover.pdf'


def execute(cfg,run,stage):
    snapshot=run/'inputs'; out=run/stage
    if stage=='validate-digital':
        from validate_digital import validate
        settings=cfg.get('validation') or {}
        epub=run/'digital'/(cfg['edition']['edition_id']+'.epub')
        if not epub.is_file():
            candidates=list((run/'digital').glob('*.epub')); need(len(candidates)==1,'Exactly one built EPUB required'); epub=candidates[0]
        validate(epub,out,settings.get('validator',{}),inside(snapshot,settings['reader_checks']) if settings.get('reader_checks') else None)
        return
    out.mkdir()
    if stage=='cover':
        from build_cover import build_cover
        from render_review import pdf_identity
        for job in jobs(cfg,'covers'):
            config_path=inside(snapshot,job['config']); spec=strict_json(config_path)
            work=run/('cover-input-'+job['id']); shutil.copytree(snapshot,work)
            local=work/job['config']; interior=local.parent/'runner-interior.pdf'
            need(not interior.exists(),'Cover helper reserved runner-interior.pdf collision')
            shutil.copyfile(pdf_target(run,'pdf'),interior)
            identity=pdf_identity(interior.read_bytes())
            # Generated interior identity only; supplied edition and template count remain authoritative.
            spec['interior'].update(path=interior.name,sha256=identity['sha256'],page_count=identity['page_count'])
            local.write_bytes(encoded(spec))
            build_cover(local,out/job['id'])
    elif stage=='render':
        from render_review import render_review
        for job in jobs(cfg,'renders'):
            work=run/('render-input-'+job['id']); work.mkdir()
            spec=strict_json(inside(snapshot,job['config']))
            shutil.copyfile(pdf_target(run,job['target']),work/'document.pdf')
            spec['pdf']='document.pdf'
            (work/'config.json').write_bytes(encoded(spec))
            render_review(work/'config.json',out/job['id'])
    elif stage=='review':
        from aggregate_reviews import aggregate_reviews
        for job in jobs(cfg,'reviews'):
            work=run/('review-input-'+job['id']); work.mkdir()
            shutil.copyfile(pdf_target(run,job['target']),work/'document.pdf')
            packets=[]
            for pid in job['packets']:
                path=run/'render'/pid/'manifest.json'
                packets.append({'path':str(path),'sha256':sha(path.read_bytes())})
            spec={'schema_version':1,'pdf':'document.pdf','packets':packets}
            if job.get('dispositions'): spec['dispositions']=strict_json(inside(snapshot,job['dispositions']))
            (work/'config.json').write_bytes(encoded(spec))
            aggregate_reviews(work/'config.json',out/job['id'])
    elif stage=='source-report':
        from report_sources import report
        work=run/'source-evidence'; work.mkdir(); shutil.copytree(snapshot,work/'inputs')
        (work/'outputs').mkdir()
        for name in cfg['source_report']['stages']: shutil.copytree(run/name,work/'outputs'/name)
        # All source/destination locators stay supplied; no inferred source use.
        shutil.copyfile(inside(snapshot,cfg['source_report']['record']),work/'source-use.json')
        report(work,'source-use.json',out,'report')
    elif stage=='package':
        from aggregate_reviews import validate_aggregate
        from build_cover import validate_cover_pair
        spec=cfg['package']; evidence={}; review_states={}; findings=[]
        bindings={'reviews':[],'covers':[],'validation':None}
        shutil.copytree(snapshot,out/'inputs')
        (out/'evidence').mkdir()
        for name in spec['stages']:
            shutil.copytree(run/name,out/name)
            evidence[name]=inventory(out/name)
        for rid in spec['required_reviews']:
            job=next(j for j in jobs(cfg,'reviews') if j['id']==rid)
            aggregate=out/'review'/rid/'manifest.json'
            work=out/'evidence'/('review-'+rid); work.mkdir()
            pdf=work/'document.pdf'; shutil.copyfile(pdf_target(run,job['target']),pdf)
            value=strict_json(aggregate); packets={}
            packet_bindings={}
            for index,packet in enumerate(value['packets']):
                destination=work/('packet-'+str(index))
                candidates=[run/'render'/pid/'manifest.json' for pid in job['packets']]
                current=next((p for p in candidates if sha(p.read_bytes())==packet['sha256']),None)
                need(current is not None,'Current run has no exact review packet for aggregate')
                shutil.copytree(current.parent,destination)
                packets[packet['sha256']]=destination/'manifest.json'
                packet_bindings[packet['sha256']]=(destination/'manifest.json').relative_to(out).as_posix()
            validated=validate_aggregate(aggregate,pdf,packets)
            review_states[rid]=validated['review_state']
            bindings['reviews'].append({'manifest':aggregate.relative_to(out).as_posix(),'pdf':pdf.relative_to(out).as_posix(),'packets':packet_bindings})
        if 'cover' in spec['stages']:
            for job in jobs(cfg,'covers'):
                work=out/'evidence'/('cover-'+job['id']); work.mkdir()
                pdf=work/'interior.pdf'; shutil.copyfile(pdf_target(run,'pdf'),pdf)
                manifest=out/'cover'/job['id']/'manifest.json'
                validate_cover_pair(manifest,pdf)
                bindings['covers'].append({'manifest':manifest.relative_to(out).as_posix(),'interior':pdf.relative_to(out).as_posix()})
                findings.append({'area':'barcode','state':'unassessed','detail':'Supplied barcode image placement is not barcode verification or physical scan acceptance.'})
        if 'validate-digital' in spec['stages']:
            validation=strict_json(out/'validate-digital/validation.json')
            work=out/'evidence'/'validation'; work.mkdir()
            epub=work/'document.epub'
            candidates=list((run/'digital').glob('*.epub'))
            need(len(candidates)==1,'One current EPUB required for validation evidence')
            shutil.copyfile(candidates[0],epub)
            need(sha(epub.read_bytes())==validation['epub']['sha256'],'Packaged validation EPUB identity mismatch')
            automated=validation['automated_validation']
            if automated.get('report'):
                report=out/'validate-digital'/automated['report']['path']
                need(sha(report.read_bytes())==automated['report']['sha256'],'Validator report changed before packaging')
            bindings['validation']={'manifest':'validate-digital/validation.json','epub':epub.relative_to(out).as_posix()}
            if automated['state']!='passed': findings.append({'area':'epub-validator','state':automated['state'],'detail':'See exact automated validation report.'})
            readers=validation['reader_checks']
            if readers['state']!='recorded' or any(c['status'] not in ('passed','not-applicable') for c in readers['checks']):
                findings.append({'area':'epub-reader','state':readers['state'],'detail':'Reader evidence is incomplete, stale, failed or unrun.'})
        elif 'digital' in spec['stages']:
            findings.append({'area':'epub-validator','state':'unrun','detail':'No validator stage included in candidate.'})
        if 'source-report' in spec['stages']:
            source_input=out/'evidence'/'source-inputs'; source_input.mkdir()
            shutil.copytree(snapshot,source_input/'inputs'); (source_input/'outputs').mkdir()
            for name in cfg['source_report']['stages']: shutil.copytree(run/name,source_input/'outputs'/name)
            shutil.copyfile(inside(snapshot,cfg['source_report']['record']),source_input/'source-use.json')
            sources=strict_json(out/'source-report/report/source-coverage.json')
            for source in sources['sources']:
                if source['source_verification']!='verified-file-access' or source['excerpt_verification']=='stale-excerpt-hash' or any(d['verification']!='verified-destination-file' or d['source_provenance']=='stale-or-unavailable' for d in source['destinations']):
                    findings.append({'area':'source-coverage','state':'stale-or-unavailable','source_id':source['source_id'],'detail':'See source-coverage.json for exact per-file and excerpt findings.'})
        pending=[rid for rid,state in review_states.items() if state!='accepted']
        # This helper only assembles a local candidate, even when human records are accepted.
        result={'schema_version':1,'edition_id':cfg['edition']['edition_id'],'status':'local-candidate','review_state':'pending' if not review_states or pending else 'accepted-records','pending_reviews':pending,'review_records':review_states,'readiness_findings':findings,'evidence_bindings':bindings,'files':evidence,'input_hashes':inventory(snapshot),'limitations':'Local package assembly is not final acceptance, printer validation, upload, publication or distribution. Relative evidence_bindings support reopening exact copied review packets and cover/interior pairs.'}
        (out/'handoff.md').write_text('# Local candidate handoff\n\nEdition: '+cfg['edition']['edition_id']+'\n\nStatus: local-candidate; review state: '+result['review_state']+'\n\n'+result['limitations']+'\n',encoding='utf-8')
        result['payload_hashes']=inventory(out)
        (out/'package-manifest.json').write_bytes(encoded(result))
        validate_package(out/'package-manifest.json')


def validate_package(manifest_path):
    """Reopen a relocated local candidate using its relative evidence bindings."""
    from aggregate_reviews import validate_aggregate
    from build_cover import validate_cover_pair
    path=Path(manifest_path).resolve(strict=True); root=path.parent; manifest=strict_json(path)
    need(manifest.get('status')=='local-candidate','Not a local candidate manifest')
    actual=inventory(root)
    actual.pop(path.name,None)
    need(actual==manifest['payload_hashes'],'Packaged payload changed or unexpected files present')
    for name,digest in manifest['payload_hashes'].items():
        need(sha(inside(root,name).read_bytes())==digest,'Packaged payload changed: '+name)
    for binding in manifest['evidence_bindings']['reviews']:
        validate_aggregate(inside(root,binding['manifest']),inside(root,binding['pdf']),{digest:inside(root,name) for digest,name in binding['packets'].items()})
    for binding in manifest['evidence_bindings']['covers']:
        validate_cover_pair(inside(root,binding['manifest']),inside(root,binding['interior']))
    binding=manifest['evidence_bindings']['validation']
    if binding:
        validation=strict_json(inside(root,binding['manifest']))
        need(sha(inside(root,binding['epub']).read_bytes())==validation['epub']['sha256'],'Packaged validator EPUB changed')
    return manifest
