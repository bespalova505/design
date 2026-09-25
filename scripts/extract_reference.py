#!/usr/bin/env python3
"""Build a searchable inventory and a small, explicit portable token adaptation."""
import csv, io, json, re
from collections import Counter, defaultdict
from pathlib import Path
from lxml import html
from archive_site import ROOT, RAW, DATA, write, dump

def css_rules(text, context=()):
    text=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    start=0; quote=None; escaped=False; depth=0; prelude=''; opened=0
    for i,ch in enumerate(text):
        if escaped: escaped=False; continue
        if ch=='\\': escaped=True; continue
        if quote:
            if ch==quote: quote=None
            continue
        if ch in ('"',"'"): quote=ch; continue
        if ch=='{' and depth==0:
            prelude=text[start:i].strip(); opened=i+1
        if ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:
                body=text[opened:i]
                if prelude.startswith(('@media','@supports','@container','@layer')):
                    yield from css_rules(body,context+(prelude,))
                else: yield {'selector':prelude,'context':list(context),'body':body.strip()}
                start=i+1
            elif depth<0: depth=0; start=i+1

def declarations(body):
    return dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+)',body))

def main():
    manifest=json.loads((DATA/'archive-manifest.json').read_text())
    css_asset=next(a for a in manifest['assets'] if '.webflow.' in a['url'] and a['url'].endswith('.css'))
    sources=[(str(Path('archive/raw')/css_asset['path']),(RAW/css_asset['path']).read_text())]
    sg=html.fromstring((RAW/'dev/style-guide/index.html').read_bytes())
    for i,el in enumerate(sg.xpath('//style')):
        name=f'extracted/inline/global-{i:02d}.css'; write(ROOT/name,el.text or '')
        sources.append((name,el.text or ''))
    records=[]; root_blocks=[]; classes=defaultdict(list)
    for path,css in sources:
        for r in css_rules(css):
            r['source']=path
            if r['selector']==':root':
                values=declarations(r['body']); root_blocks.append({**r,'values':values})
                for name,value in values.items(): records.append({'name':name,'value':value.strip(),'context':r['context'],'source':path,'references':re.findall(r'var\((--[\w-]+)',value)})
            for cls in set(re.findall(r'\.([a-zA-Z_][\w-]*)',r['selector'])):
                classes[cls].append({'selector':r['selector'],'context':r['context'],'source':path,'variables':sorted(set(re.findall(r'var\((--[\w-]+)',r['body'])))})
    usage=defaultdict(set); outlines=[]
    for pg in manifest['pages']:
        doc=html.fromstring((RAW/pg['path']).read_bytes())
        for el in doc.xpath('//*[@class]'):
            for cls in el.get('class').split(): usage[cls].add(pg['url'])
        sections=[]
        for el in doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " styleguide_heading ")]'):
            sections.append(' '.join(el.text_content().split()))
        outlines.append({'url':pg['url'],'path':pg['path'],'title':pg['title'],'headings':pg['headings'],'styleguide_sections':sections})
    all_classes=[{'name':c,'category':'webflow-runtime' if c.startswith('w-') else 'documentation' if c.startswith(('styleguide_','designguide_')) else 'custom-component' if '_' in c else 'utility-or-variant','used_on':sorted(usage.get(c,[])),'rules':rs} for c,rs in sorted(classes.items())]
    dump(DATA/'tokens.reference.json',{'status':'extracted-original-including-known-defects','source':manifest['source'],'retrieved_at':manifest['retrieved_at'],'records':records})
    dump(DATA/'class-catalog.json',all_classes)
    dump(DATA/'page-catalog.json',outlines)
    out=io.StringIO(); w=csv.writer(out,lineterminator='\n'); w.writerow(['name','value','context','source'])
    for r in records: w.writerow([r['name'],r['value'],' | '.join(r['context']),r['source']])
    write(DATA/'tokens.reference.csv',out.getvalue())
    original_css=[]; fixed_css=[]; adapted=[]
    for block in root_blocks:
        vals=dict(block['values']); context=block['context']
        def render(v,c):
            text=':root {\n'+''.join(f'  {k}: {value.strip()};\n' for k,value in v.items())+'}'
            for layer in reversed(c): text=layer+' {\n'+text+'\n}'
            return text
        original_css.append(render(vals,context))
        if not context:
            # In the source these aliases cycle when h6 switches on tablet / portrait.
            if '--heading--md--h6' in vals: vals['--heading--md--h6']='1.25rem'
            if '--heading--xs--h6' in vals: vals['--heading--xs--h6']='var(--heading--sm--h6)'
        context=[c.replace('(max-width: 478)','(max-width: 479px)') for c in context]
        fixed_css.append(render(vals,context))
        adapted.append({'context':context,'values':vals})
    write(ROOT/'extracted/tokens.reference.css','/* Original token declarations; includes source defects. */\n\n'+'\n\n'.join(original_css)+'\n')
    write(ROOT/'portable/tokens.css','/* Adaptation, 2026-09-25. Source: Caleb Raney Variable Design System.\n   Fixes: 479px portrait query; cyclic md/xs H6 aliases. See docs/04-source-issues.md. */\n\n'+'\n\n'.join(fixed_css)+'\n')
    dump(ROOT/'portable/tokens.json',{'status':'adapted-css-token-records-not-a-figma-import','blocks':adapted})
    doc=html.fromstring((RAW/'dev/components/index.html').read_bytes())
    feature=doc.xpath('//section[contains(@class,"section_feature-split")]')[0]
    write(ROOT/'extracted/components/feature-split.original.html',html.tostring(feature,encoding='unicode',pretty_print=True))
    buttons=[]
    for e in sg.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," button ")]'):
        c=e.get('class'); text=' '.join(e.text_content().split())
        if not any(b['classes']==c for b in buttons): buttons.append({'classes':c,'text':text,'tag':e.tag,'html':html.tostring(e,encoding='unicode')})
    dump(DATA/'button-variants.json',buttons)
    write(ROOT/'extracted/components/button-variants.original.html','\n\n'.join(b['html'] for b in buttons)+'\n')
    form=sg.xpath('//form')[0]
    write(ROOT/'extracted/components/form.original.html',html.tostring(form,encoding='unicode',pretty_print=True))
    summary={'public_pages':len(manifest['pages']),'downloaded_assets':sum(bool(a.get('path')) for a in manifest['assets']),'failed_assets':[a for a in manifest['assets'] if not a.get('path')],'unique_css_variables':len(set(r['name'] for r in records)),'token_declarations_including_breakpoint_overrides':len(records),'css_classes':len(all_classes),'classes_by_category':dict(Counter(c['category'] for c in all_classes)),'button_class_combinations':len(buttons),'composed_demo_sections':1}
    dump(DATA/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
