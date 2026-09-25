#!/usr/bin/env python3
"""Verify archive integrity, local references and responsive token graphs."""
import hashlib,json,re,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit
from lxml import html
from archive_site import ROOT,RAW,SITE,DATA,URL_CSS,dump

def active(context,width):
    for c in context:
        for op,v in re.findall(r'(max|min)-width:\s*(\d+)px',c):
            if op=='max' and width>int(v) or op=='min' and width<int(v): return False
        if re.search(r'(?:max|min)-width:\s*\d+\s*\)',c): return False
    return True

def token_graph(blocks,width):
    values={}
    for b in blocks:
        if active(b['context'],width): values.update(b['values'])
    cycles=set();missing=set();done=set()
    def visit(n,trail):
        if n in trail:
            cycles.add(tuple(sorted(trail[trail.index(n):])));return
        if n not in values: missing.add(n);return
        if n in done:return
        for target in re.findall(r'var\((--[\w-]+)',values[n]):visit(target,trail+[n])
        done.add(n)
    for n in values:visit(n,[])
    return {'width':width,'cycles':[list(c) for c in sorted(cycles)],'missing':sorted(missing),'variables':len(values)}

def main():
    m=json.loads((DATA/'archive-manifest.json').read_text()); failures=[];raw_count=0
    for r in m['pages']+m['assets']:
        if not r.get('path'):continue
        p=RAW/r['path'];raw_count+=1
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:failures.append({'file':str(p),'error':'SHA-256 mismatch'})
    broken=[];external_assets=set();refs=0
    def check(ref,p,asset=False):
        nonlocal refs
        if not ref or ref.startswith(('data:','blob:','#','mailto:','javascript:','tel:')):return
        u=urlsplit(ref)
        if u.scheme or u.netloc:
            if asset:external_assets.add(ref)
            return
        refs+=1
        target=(p.parent/unquote(u.path)).resolve()
        if not target.exists():broken.append({'file':str(p.relative_to(ROOT)),'reference':ref})
    for p in SITE.rglob('*.html'):
        d=html.fromstring(p.read_bytes())
        for e in d.xpath('//*[@href or @src or @srcset or @poster]'):
            for a in ['href','src','poster']:
                if e.get(a):check(e.get(a),p,e.tag in ['img','script','iframe'] or e.get('rel')=='stylesheet')
            if e.get('srcset'):
                for item in e.get('srcset').split(','):check(item.strip().split()[0],p,True)
    for p in SITE.rglob('*.css'):
        for ref in URL_CSS.findall(p.read_text()):check(ref,p,True)
    records=json.loads((DATA/'tokens.reference.json').read_text())['records'];blocks=[]
    for r in records:
        if not blocks or blocks[-1]['context']!=r['context'] or blocks[-1]['source']!=r['source']:blocks.append({'context':r['context'],'source':r['source'],'values':{}})
        blocks[-1]['values'][r['name']]=r['value']
    adapted=json.loads((ROOT/'portable/tokens.json').read_text())['blocks']
    original_checks=[token_graph(blocks,w) for w in [1280,900,600,390]]
    portable_checks=[token_graph(adapted,w) for w in [1280,900,600,390]]
    for c in portable_checks:
        if c['cycles'] or c['missing']:failures.append({'portable_tokens':c})
    if not any(c['cycles'] for c in original_checks):failures.append({'source_evidence':'Expected tablet H6 cycle was not reproduced'})
    if broken:failures.append({'broken_local_references':broken})
    report={'status':'pass' if not failures else 'fail','raw_files_verified':raw_count,'local_references_checked':refs,'broken_local_references':broken,'integrity_failures':failures,'external_asset_references_remaining':sorted(external_assets),'known_unavailable_assets':[r for r in m['assets'] if not r.get('path')],'original_token_graphs':original_checks,'portable_token_graphs':portable_checks,'scope':'Integrity/link and token dependency checks, not a full cross-browser UI audit.'}
    dump(ROOT/'evidence/verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2));sys.exit(bool(failures))

if __name__=='__main__':main()
