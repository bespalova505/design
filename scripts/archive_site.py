#!/usr/bin/env python3
"""Archive the public Variable Design System, without private Webflow APIs.

Run: python3 scripts/archive_site.py (requires lxml)
Original HTTP bodies are retained in archive/raw; browse archive/site over HTTP.
External documentation and videos remain links rather than recursive crawls.
"""
from __future__ import annotations
import concurrent.futures, hashlib, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, quote
from urllib.request import Request, urlopen
from lxml import html, etree

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://variable-design-system.webflow.io'
RAW, SITE, DATA = ROOT/'archive/raw', ROOT/'archive/site', ROOT/'data'
HEADERS = {'User-Agent': 'VariableDesignResearchArchive/1.0 (public reference archive)', 'Accept-Encoding': 'identity'}
URL_CSS = re.compile(r'url\(\s*[\"\']?([^\s\)\"\']+)[\"\']?\s*\)')

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))

def dump(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

def canonical(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path or '/', p.query, ''))

def fetch(url):
    started = time.monotonic()
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=40) as r:
            body = r.read()
            return {'url': url, 'final_url': r.url, 'status': r.status,
                    'content_type': r.headers.get('Content-Type',''), 'bytes':len(body),
                    'sha256':hashlib.sha256(body).hexdigest(), 'body':body,
                    'seconds':round(time.monotonic()-started,2)}
    except Exception as e:
        return {'url':url, 'status':None, 'error':str(e)}

def page_path(url):
    return Path(urlsplit(url).path.strip('/') or '.')/'index.html'

def asset_path(url):
    p = urlsplit(url)
    name = re.sub(r'[^A-Za-z0-9._-]', '-', unquote(p.path.rsplit('/',1)[-1])) or 'resource'
    if '.' not in name:
        name += '.css' if p.netloc=='fonts.googleapis.com' else '.bin'
    return Path('assets')/p.netloc/(hashlib.sha256(url.encode()).hexdigest()[:12]+'-'+name)

def run():
    stamp = datetime.now(timezone.utc).isoformat()
    pages, assets, queue, attempted = {}, {}, [BASE+'/'], set()
    external, embeds, font_urls = set(), set(), set()
    infrastructure = []
    for p in ['/robots.txt','/sitemap.xml']:
        r=fetch(BASE+p); infrastructure.append({k:v for k,v in r.items() if k!='body'})
        if r.get('body') is not None:
            write(RAW/p.lstrip('/'),r['body']); write(SITE/p.lstrip('/'),r['body'])
            if p.endswith('.xml'):
                queue += [canonical(u.strip()) for u in etree.fromstring(r['body']).xpath('//*[local-name()="loc"]/text()')]
    asset_queue = set()
    def add_asset(ref, origin):
        if ref and not ref.startswith(('data:','blob:','#','mailto:','javascript:')):
            u=canonical(urljoin(origin,ref))
            if urlsplit(u).scheme in ('http','https'): asset_queue.add(u)
    while queue:
        url=canonical(queue.pop(0))
        if url in attempted: continue
        attempted.add(url)
        r=fetch(url); pages[url]=r
        if not r.get('body'): continue
        r['path']=page_path(url).as_posix()
        write(RAW/r['path'],r['body'])
        doc=html.fromstring(r['body'],base_url=url)
        r['title']=''.join(doc.xpath('//title/text()'))
        r['headings']=[{'level':int(e.tag[1]),'text':' '.join(e.text_content().split()),'id':e.get('id')} for e in doc.xpath('//h1|//h2|//h3|//h4|//h5|//h6')]
        r['last_published']=(re.findall(r'Last Published: (.*?)-->',r['body'].decode(errors='replace')) or [None])[0]
        r['internal_links']=[]
        for a in doc.xpath('//a[@href]'):
            ref=a.get('href'); u=canonical(urljoin(url,ref))
            if urlsplit(u).netloc==urlsplit(BASE).netloc:
                r['internal_links'].append(u)
                if not Path(urlsplit(u).path).suffix or Path(urlsplit(u).path).suffix=='.html': queue.append(u)
                else: add_asset(u,url)
            elif urlsplit(u).scheme in ('http','https'): external.add(u)
        for el in doc.xpath('//*[@src]'):
            if el.tag=='iframe': embeds.add(urljoin(url,el.get('src')))
            else: add_asset(el.get('src'),url)
        for el in doc.xpath('//link[@href]'):
            if el.get('rel','').lower() in ('stylesheet','icon','shortcut icon','apple-touch-icon','preload'): add_asset(el.get('href'),url)
        for el in doc.xpath('//*[@srcset]'):
            for item in el.get('srcset').split(','): add_asset(item.strip().split(' ')[0],url)
        for el in doc.xpath('//*[@poster]'): add_asset(el.get('poster'),url)
        for text in doc.xpath('//style/text()|//@style'):
            for ref in URL_CSS.findall(text): add_asset(ref,url)
        for text in doc.xpath('//script[not(@src)]/text()'):
            if 'WebFont.load' in text:
                fam = re.search(r'families\s*:\s*\[([^\]]+)\]',text)
                if fam:
                    families = re.findall(r'[\"\']([^\"\']+)[\"\']',fam.group(1))
                    fu='https://fonts.googleapis.com/css?family='+quote('|'.join(families),safe=':|,')
                    font_urls.add(fu); add_asset(fu,url)
            if 'w-json' in ''.join(doc.xpath('//script/@class')) and ('loom.com' in text or 'youtube.com' in text):
                for u in re.findall(r'https?://[^\s\"<>]+',text): embeds.add(u)
        print('page',r['path'],r['bytes'],flush=True)
    while asset_queue:
        pending=sorted(asset_queue-set(assets)); asset_queue.clear()
        if not pending: break
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            for r in pool.map(fetch,pending):
                u=r['url']; assets[u]=r
                if not r.get('body'):
                    print('asset failed',u,r.get('error'),flush=True); continue
                r['path']=asset_path(u).as_posix()
                write(RAW/r['path'],r['body'])
                if 'text/css' in r['content_type'] or urlsplit(u).path.endswith('.css'):
                    for ref in URL_CSS.findall(r['body'].decode(errors='replace')): add_asset(ref,u)
        print('assets downloaded',sum('body' in a for a in assets.values()),flush=True)
    lookup={u:Path(r['path']) for u,r in {**pages,**assets}.items() if 'path' in r}
    def localize(ref,origin,current):
        if not ref or ref.startswith(('data:','blob:','mailto:','tel:','javascript:','#')): return ref
        absolute=urljoin(origin,ref); frag=urlsplit(absolute).fragment
        target=lookup.get(canonical(absolute))
        if target is None: return ref
        return os.path.relpath(target,Path(current).parent).replace(os.sep,'/')+('#'+frag if frag else '')
    for url,r in assets.items():
        if 'path' not in r: continue
        data=r['body']
        if 'text/css' in r['content_type'] or urlsplit(url).path.endswith('.css'):
            data=URL_CSS.sub(lambda m:'url("'+localize(m.group(1),url,r['path'])+'")',data.decode(errors='replace'))
        write(SITE/r['path'],data)
    for url,r in pages.items():
        if 'path' not in r: continue
        doc=html.fromstring(r['body'],base_url=url)
        for el in doc.iter():
            if not isinstance(el.tag,str): continue
            for attr in ['href','src','poster']:
                if el.get(attr):
                    old=el.get(attr); new=localize(old,url,r['path']); el.set(attr,new)
                    if old!=new and el.get('integrity'): el.attrib.pop('integrity',None)
            if el.get('srcset'):
                el.set('srcset',', '.join(' '.join([localize(item.strip().split()[0],url,r['path']),*item.strip().split()[1:]]) for item in el.get('srcset').split(',') if item.strip()))
            if el.get('style'): el.set('style',URL_CSS.sub(lambda m:'url("'+localize(m.group(1),url,r['path'])+'")',el.get('style')))
            if el.tag=='style' and el.text: el.text=URL_CSS.sub(lambda m:'url("'+localize(m.group(1),url,r['path'])+'")',el.text)
            # Replace the Google WebFont request with a local CSS dependency.
            if el.tag=='script' and el.text and 'WebFont.load' in el.text:
                for fu in sorted(font_urls):
                    link=html.Element('link',rel='stylesheet',href=localize(fu,url,r['path']))
                    doc.find('head').append(link)
                el.text='/* Font CSS localized for the archive. Original initialization is in archive/raw. */'
        doc.find('head').append(etree.Comment(' Local research mirror. See provenance and limitations in README.md. '))
        write(SITE/r['path'],html.tostring(doc,encoding='utf-8',doctype='<!DOCTYPE html>'))
    clean=lambda r:{k:v for k,v in r.items() if k!='body'}
    manifest={'source':BASE,'retrieved_at':stamp,'scope':'Public same-origin sitemap and recursively linked HTML; referenced static assets and CSS dependencies.',
              'pages':[clean(r) for r in pages.values()], 'assets':[clean(r) for r in assets.values()],
              'infrastructure':infrastructure,'external_links':sorted(external),'external_embeds':sorted(embeds),
              'limitations':['Not an authenticated Webflow Designer project export.','No unpublished pages or CMS database.','External documentation and video players remain references.','Forms retain demo markup; no form backend has been migrated.']}
    dump(DATA/'archive-manifest.json',manifest)
    print(json.dumps({'pages':len(pages),'assets':len(assets),'failed':sum('body' not in r for r in [*pages.values(),*assets.values()]),'bytes':sum(r.get('bytes',0) for r in [*pages.values(),*assets.values()])}),flush=True)

if __name__=='__main__': run()
