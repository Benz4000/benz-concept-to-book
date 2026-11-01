"""Explicit local project runner. Plan is read-only; execution requires named stages."""
import argparse
import hashlib
import importlib
import platform
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
DEPS = {'import': [], 'prepare': ['import'], 'digital': ['prepare'], 'pdf': ['prepare'], 'audit-digital': ['digital'], 'audit-pdf': ['pdf']}

def need(test, message):
    if not test:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')

def strict_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs)

def inside(root, name, exists=True):
    need(isinstance(name, str) and name and '\\' not in name, 'Expected relative POSIX path')
    p = PurePosixPath(name)
    need(p.as_posix() == name and not p.is_absolute() and ':' not in name and all(x not in ('..', '.') for x in p.parts), 'Path escape or ambiguous path: ' + name)
    path = root.joinpath(*p.parts)
    need(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'Path escapes root: ' + name)
    if exists:
        need(path.is_file(), 'Missing input: ' + name)
    return path

def inventory(root):
    need(not root.is_symlink(), 'Symlink stage directory forbidden')
    result = {}
    for p in sorted(root.rglob('*')):
        need(not p.is_symlink() and p.resolve().is_relative_to(root.resolve()), 'Symlink or escaped stage output forbidden')
        if p.is_file():
            result[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return result

def load_manifest(path):
    cfg = strict_json(path)
    need(isinstance(cfg, dict) and cfg.get('schema_version') == 1, 'Expected project schema_version 1')
    need(set(cfg) <= {'schema_version','input_root','selected_inputs','import','edition','print_settings','validation','covers','renders','reviews','source_report','package'}, 'Unknown project keys')
    root = Path(cfg['input_root'])
    if not root.is_absolute():
        root = Path(path).resolve().parent / root
    root = root.resolve(strict=True)
    need(root.is_dir(), 'input_root must be directory')
    selected = cfg['selected_inputs']
    need(isinstance(selected, list) and selected and len(selected) == len(set(selected)), 'selected_inputs must be nonempty unique paths')
    for name in selected:
        inside(root, name, False)
    imp = cfg['import']
    need({'manuscript','metadata'} <= set(imp) <= {'manuscript','metadata','extended_docx'}, 'Explicit manuscript/metadata and optional extended_docx required')
    need(type(imp.get('extended_docx',False)) is bool, 'extended_docx must be boolean')
    need(not imp.get('extended_docx') or Path(imp['manuscript']).suffix.lower()=='.docx', 'Extended import requires DOCX')
    edition = cfg['edition']
    need(set(edition) <= {'edition_id','formats','sections','assets','cover_image','font','image_insertions'}, 'Unknown edition keys')
    need({'edition_id','formats','sections','assets'} <= set(edition), 'Edition settings required')
    need(edition['formats'] and set(edition['formats']) <= {'html','epub'}, 'Explicit digital formats required')
    need(isinstance(edition['sections'], list) and edition['sections'], 'Explicit section roles required')
    ids = []
    for section in edition['sections']:
        need(isinstance(section, dict) and set(section) <= {'id','part','kind','title'} and {'id','part','kind'} <= set(section), 'Invalid explicit section role')
        ids.append(section['id'])
    need(len(ids) == len(set(ids)), 'Duplicate section roles')
    parts = [s['part'] for s in edition['sections']]
    need(all(p in ('front','body','back') for p in parts) and 'body' in parts and parts == sorted(parts,key=('front','body','back').index), 'Invalid or conflicting section part order')
    need(all(isinstance(s['kind'],str) and s['kind'].strip() for s in edition['sections']), 'Explicit kind required')
    required = [imp['manuscript'], imp['metadata']]
    required += [a['path'] for a in edition['assets']]
    if edition.get('font'):
        required.append(edition['font']['path'])
    if cfg.get('print_settings'):
        required.append(cfg['print_settings'])
        need(set(required) <= set(selected), 'Every directly referenced file must be selected before reading settings')
        settings_path = inside(root, cfg['print_settings'], False)
        if settings_path.is_file():
            settings = strict_json(settings_path)
            required.append(settings['font']['path'])
            required += list(settings['font'].get('variants', {}).values())
    need(set(required) <= set(selected), 'Every referenced manuscript, metadata, art, font and settings file must be selected')
    import pipeline_extensions as extensions
    extensions.selected_references(cfg,root)
    return cfg, root

def insert_images(edition, sections, apply=False):
    insertions = edition.get('image_insertions',[])
    need(isinstance(insertions,list) and len(insertions) <= 10000, 'image_insertions must be bounded list')
    by_id = {s['id']:s for s in sections}
    assets = {a['id'] for a in edition['assets']}
    seen = set()
    for item in insertions:
        need(isinstance(item,dict) and set(item) <= {'section_id','block_index','asset_id','caption'} and {'section_id','block_index','asset_id'} <= set(item), 'Invalid image insertion fields')
        sid, index = item['section_id'],item['block_index']
        need(sid in by_id and item['asset_id'] in assets, 'Unknown image insertion section or asset')
        need(type(index) is int and 0 <= index <= len(by_id[sid]['blocks']), 'Image insertion index out of range')
        need((sid,index) not in seen, 'Duplicate image insertion index; use unique original block positions')
        seen.add((sid,index))
        need('caption' not in item or isinstance(item['caption'],str) and item['caption'].strip(), 'Caption must be nonempty string')
    if apply:
        for item in sorted(insertions,key=lambda i:i['block_index'],reverse=True):
            block = {'type':'image','asset_id':item['asset_id']}
            if 'caption' in item:
                block['caption'] = item['caption']
            by_id[item['section_id']]['blocks'].insert(item['block_index'],block)

def capabilities(stages):
    runtime = {'implementation':platform.python_implementation(),'version':platform.python_version(),'executable':str(Path(sys.executable).resolve())}
    packages = {}
    if any(s in stages for s in ('pdf','audit-pdf','cover','render','review')):
        for name in ('reportlab','pypdf','PIL.Image'):
            try:
                module = importlib.import_module(name)
                packages[name] = {'available':True,'version':str(getattr(module,'__version__',getattr(module,'Version','unknown')))}
            except Exception as exc:
                packages[name] = {'available':False,'error':type(exc).__name__+': '+str(exc)}
    gaps = []
    if sys.version_info < (3,12):
        gaps.append('Python 3.12+ required')
    gaps += ['PDF dependency unavailable: '+name for name,value in packages.items() if not value['available']]
    return runtime,packages,gaps

def run(manifest, output_root, stages=None, execute=False, resume=None):
    cfg, root = load_manifest(manifest)
    import pipeline_extensions as extensions
    dependencies = extensions.dependencies(cfg,DEPS)
    out = Path(output_root).resolve(strict=True)
    need(out.is_dir() and not out.is_relative_to(root) and not root.is_relative_to(out), 'Output root must be external and disjoint from input root')
    stages = stages or []
    need(len(stages) == len(set(stages)) and set(stages) <= set(dependencies), 'Unknown or duplicate stages')
    missing = [n for n in cfg['selected_inputs'] if not inside(root, n, False).is_file()]
    conflicts = []
    for stage in stages:
        for dep in dependencies[stage]:
            if dep not in stages or stages.index(dep) > stages.index(stage):
                conflicts.append(stage + ' requires earlier requested stage ' + dep)
    if any(s in stages for s in ('pdf','audit-pdf')) and not cfg.get('print_settings'):
        conflicts.append('PDF requires explicit print_settings')
    for stage,key in [('cover','covers'),('render','renders'),('review','reviews'),('source-report','source_report'),('package','package')]:
        if stage in stages and not cfg.get(key):
            conflicts.append(stage+' requires explicit '+key+' settings')
    if 'validate-digital' in stages and 'epub' not in cfg['edition']['formats']:
        conflicts.append('validate-digital requires an explicitly selected EPUB format')
    if not missing:
        import import_manuscript as importer
        manuscript = inside(root,cfg['import']['manuscript']).read_bytes()
        importer.metadata(inside(root,cfg['import']['metadata']).read_bytes())
        suffix = Path(cfg['import']['manuscript']).suffix.lower()
        need(suffix in ('.md','.docx'), 'Unsupported manuscript format')
        units, issues, counts = importer.markdown(manuscript) if suffix == '.md' else importer.import_extended_docx.parse(manuscript,importer) if cfg['import'].get('extended_docx') else importer.docx(manuscript)
        if issues:
            conflicts.append('Importer unsupported features: '+str(issues))
        else:
            sections, coverage = importer.convert(units)
            insert_images(cfg['edition'],sections)
            generated = {'edition.json','import-manifest.json'} | {s['source'] for s in sections}
            collisions = generated.intersection(set(cfg['selected_inputs']) - set(cfg['import'].values()))
            if collisions:
                conflicts.append('Selected file conflicts with generated imported output: '+str(sorted(collisions)))
            if [s['id'] for s in sections] != [s['id'] for s in cfg['edition']['sections']]:
                conflicts.append('Explicit section IDs/order do not match importer section boundaries')
    runtime, packages, capability_gaps = capabilities(stages)
    conflicts += capability_gaps
    optional_tools = {stage:extensions.tools(cfg,stage,root) for stage in stages if stage in extensions.STAGES}
    plan = {'runtime':runtime,'pdf_dependencies':packages,'optional_tools':optional_tools,'capability_gaps':capability_gaps,'schema_version':1,'mode':'execute' if execute else 'plan','dependencies':dependencies,'missing_inputs':missing,'conflicts':conflicts,'proposed_actions':stages,'selected_inputs':cfg['selected_inputs']}
    if not execute:
        return plan
    need(stages and not missing and not conflicts, 'Execution requires explicit stages and no missing inputs or conflicts')
    old = None
    if resume:
        oldroot = Path(resume).resolve(strict=True)
        need(oldroot.is_dir() and oldroot.is_relative_to(out), 'Resume must be prior run beneath output root')
        old = strict_json(oldroot / 'run-manifest.json')
        need(old.get('schema_version') == 1 and isinstance(old.get('stages'), dict), 'Invalid resume manifest')
    target = out / ('run-' + uuid.uuid4().hex)
    target.mkdir()
    snapshot = target / 'inputs'
    snapshot.mkdir()
    for name in cfg['selected_inputs']:
        dest = inside(snapshot, name, False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(inside(root,name).read_bytes())
    state = dict(plan, run_id=target.name, input_hashes=inventory(snapshot), project=cfg, stages={}, status='running')
    def save():
        (target / 'run-manifest.json').write_bytes(encoded(state))
    save()
    for stage in stages:
        helper = 'pipeline_extensions.py' if stage in extensions.STAGES else {'import':'import_manuscript.py','prepare':'run_project.py','digital':'build_reading_edition.py','pdf':'build_print_edition.py','audit-digital':'audit_exports.py','audit-pdf':'audit_exports.py'}[stage]
        if stage in extensions.STAGES:
            names = extensions.relevant_inputs(cfg,snapshot,stage)
            relevant = {p:state['input_hashes'][p] for p in names}
            settings = extensions.stage_settings(cfg,stage)
        elif stage == 'import':
            relevant = {k: state['input_hashes'][cfg['import'][k]] for k in ('manuscript','metadata')}
            settings = cfg['import']
        elif stage == 'prepare':
            names = [a['path'] for a in cfg['edition']['assets']]
            if cfg['edition'].get('font'):
                names.append(cfg['edition']['font']['path'])
            relevant = {p:state['input_hashes'][p] for p in names}
            settings = cfg['edition']
        elif stage == 'pdf':
            settings = cfg['print_settings']
            print_cfg = strict_json(inside(snapshot,settings))
            names = [settings, print_cfg['font']['path']] + list(print_cfg['font'].get('variants',{}).values())
            relevant = {p:state['input_hashes'][p] for p in names}
        else:
            relevant, settings = {}, None
        helper_hashes = {helper:sha((HERE/helper).read_bytes())}
        helper_hashes['rich_content.py']=sha((HERE/'rich_content.py').read_bytes())
        if stage=='import':helper_hashes['import_extended_docx.py']=sha((HERE/'import_extended_docx.py').read_bytes())
        extension_helpers = {'validate-digital':['validate_digital.py'],'cover':['build_cover.py','render_review.py','verify_barcode.py'],'render':['render_review.py'],'review':['aggregate_reviews.py','render_review.py'],'source-report':['report_sources.py'],'package':['aggregate_reviews.py','render_review.py','build_cover.py','validate_digital.py']}
        for name in extension_helpers.get(stage,[]):
            if (HERE/name).is_file():
                helper_hashes[name] = sha((HERE/name).read_bytes())
        if (HERE/'semantic_content.py').is_file():
            helper_hashes['semantic_content.py'] = sha((HERE/'semantic_content.py').read_bytes())
        helper_hashes['build_reading_edition.py'] = sha((HERE/'build_reading_edition.py').read_bytes())
        if stage == 'audit-pdf':
            helper_hashes['build_print_edition.py'] = sha((HERE/'build_print_edition.py').read_bytes())
        fingerprint_components = {'inputs':relevant,'settings':settings,'helpers':helper_hashes,'runtime':runtime,'packages':packages if stage in ('pdf','audit-pdf','cover','render','review') else {},'dependencies':{d:state['stages'][d]['outputs'] for d in dependencies[stage]}}
        if stage in extensions.STAGES:
            fingerprint_components['tools'] = optional_tools[stage]
        fingerprint = sha(encoded(fingerprint_components))
        stageout = target / stage
        prior = old.get('stages',{}).get(stage,{}) if old else {}
        if prior.get('status') == 'complete' and prior.get('fingerprint') == fingerprint:
            prior_dir = oldroot / stage
            if prior_dir.is_dir() and inventory(prior_dir) == prior.get('outputs'):
                shutil.copytree(prior_dir,stageout)
                state['stages'][stage] = dict(prior,reused_from=str(oldroot))
                save()
                continue
        state['stages'][stage] = {'status':'running','fingerprint':fingerprint,'fingerprint_components':fingerprint_components}
        save()
        try:
            prepared = target / 'prepare'
            if stage in extensions.STAGES:
                extensions.execute(cfg,target,stage)
            elif stage == 'prepare':
                shutil.copytree(target/'import', stageout)
                for name in relevant:
                    if name not in cfg['import'].values():
                        dest = inside(stageout,name,False)
                        need(not dest.exists(), 'Selected input conflicts with imported output: '+name)
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        dest.write_bytes(inside(snapshot,name).read_bytes())
                edition = strict_json(stageout/'edition.json')
                roles = cfg['edition']['sections']
                need([s['id'] for s in edition['sections']] == [s['id'] for s in roles], 'Explicit section IDs/order must match import; inspect importer preflight')
                for section, role in zip(edition['sections'],roles):
                    section.update(role)
                imported_sections = []
                for section in edition['sections']:
                    imported_sections.append(dict(section,**strict_json(inside(stageout,section['source']))))
                insert_images(cfg['edition'],imported_sections,True)
                for section in imported_sections:
                    inside(stageout,section['source']).write_bytes(encoded({'blocks':section['blocks']}))
                edition.update({k:v for k,v in cfg['edition'].items() if k not in ('sections','image_insertions')})
                (stageout/'edition.json').write_bytes(encoded(edition))
            else:
                if stage == 'pdf':
                    prepared = target / 'pdf-input'
                    shutil.copytree(target/'prepare',prepared)
                    for name in cfg['selected_inputs']:
                        if name not in cfg['import'].values() and name not in inventory(prepared):
                            dest = inside(prepared,name,False)
                            dest.parent.mkdir(parents=True,exist_ok=True)
                            dest.write_bytes(inside(snapshot,name).read_bytes())
                elif stage == 'audit-pdf':
                    prepared = target / 'pdf-input'
                    if not prepared.exists():
                        shutil.copytree(target/'prepare',prepared)
                        for name in cfg['selected_inputs']:
                            if name not in cfg['import'].values() and name not in inventory(prepared):
                                dest = inside(prepared,name,False)
                                dest.parent.mkdir(parents=True,exist_ok=True)
                                dest.write_bytes(inside(snapshot,name).read_bytes())
                command = [sys.executable,'-B',str(HERE/helper)]
                if stage == 'import':
                    command += ['--input-root',str(snapshot),'--input',cfg['import']['manuscript'],'--metadata',cfg['import']['metadata'],'--output-root',str(target),'--output-dir',stage]
                    if cfg['import'].get('extended_docx'):command.append('--extended-docx')
                elif stage.startswith('audit-'):
                    command += ['--input-root',str(prepared),'--config','edition.json','--release-root',str(target/DEPS[stage][0])]
                    if stage == 'audit-pdf':
                        command += ['--settings',cfg['print_settings']]
                else:
                    command += ['--input-root',str(prepared),'--config','edition.json','--output-root',str(target),'--output-dir',stage]
                    if stage == 'pdf':
                        command += ['--settings',cfg['print_settings']]
                result = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',shell=False)
                if stage.startswith('audit-'):
                    stageout.mkdir()
                if not stageout.exists():
                    stageout.mkdir()
                (stageout/'runner-stdout.txt').write_text(result.stdout,encoding='utf-8')
                (stageout/'runner-stderr.txt').write_text(result.stderr,encoding='utf-8')
                need(result.returncode == 0, 'Helper failed: '+stage+'; inspect retained runner logs')
            state['stages'][stage].update(status='complete',outputs=inventory(stageout))
            save()
        except Exception as exc:
            state['stages'][stage].update(status='incomplete',error=str(exc))
            state['status'] = 'incomplete'
            save()
            raise ValueError(str(exc)+'; retained run '+str(target)) from exc
    state['status'] = 'complete'
    save()
    return {'status':'complete','run_directory':str(target),'stages':state['stages']}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--output-root',required=True,type=Path)
    p.add_argument('--stages',help='Comma-separated stages in dependency order; no implicit actions')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--resume',type=Path)
    a = p.parse_args(argv)
    try:
        print(encoded(run(a.manifest,a.output_root,a.stages.split(',') if a.stages else [],a.execute,a.resume)).decode('utf-8'))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'refused','error':str(exc)}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
