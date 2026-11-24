"""Development-only rendered-browser verification using an installed Chrome.

No model, project DB, existing browser profile, credentials or app writes are used.
Requires the development environment's websockets package; not imported by Streamlit.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

import websockets

ROOT=Path(__file__).resolve().parents[1]
URL='https://rayban-brand-contagion-tracker-ketx7kggvl3vh2sdpvtnf4.streamlit.app/'
RELEASE='hec-analysis-2026-11-24-v4'


async def inspect(socket_url, timeout, observe_only, *, story=False, mobile=False):
    async with websockets.connect(socket_url,max_size=12_000_000,proxy=None) as socket:
        sequence=0
        contexts=set()
        sessions={None}
        enabled={None}
        active=None
        async def call(method,params=None,session=None):
            nonlocal sequence
            sequence+=1; request_id=sequence
            request={'id':request_id,'method':method,'params':params or {}}
            if session:request['sessionId']=session
            await socket.send(json.dumps(request))
            while True:
                message=json.loads(await asyncio.wait_for(socket.recv(),timeout=15))
                if message.get('method')=='Runtime.executionContextCreated':
                    context=message['params']['context']
                    if context.get('auxData',{}).get('isDefault'):
                        contexts.add((message.get('sessionId'),context['id']))
                elif message.get('method')=='Runtime.executionContextsCleared':
                    contexts.difference_update([c for c in contexts if c[0]==message.get('sessionId')])
                elif message.get('method')=='Runtime.executionContextDestroyed':
                    contexts.discard((message.get('sessionId'),message['params']['executionContextId']))
                elif message.get('method')=='Target.attachedToTarget':
                    sessions.add(message['params']['sessionId'])
                if message.get('id')==request_id:
                    if message.get('error'):raise RuntimeError(message['error'])
                    return message.get('result',{})
        async def evaluate(expression,context=None):
            selected=context or active
            params={'expression':expression,'returnByValue':True}
            if selected:params['contextId']=selected[1]
            result=await call('Runtime.evaluate',params,session=selected[0] if selected else None)
            if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
            return result.get('result',{}).get('value')
        await call('Page.enable')
        if mobile:
            await call('Emulation.setDeviceMetricsOverride', {'width':390, 'height':844,
                       'deviceScaleFactor':1, 'mobile':True})
        await call('Runtime.enable')
        await call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':False,'flatten':True})
        deadline=time.monotonic()+timeout
        snapshot={}
        while True:
            active=None
            for session in list(sessions-enabled):
                await call('Runtime.enable',session=session)
                enabled.add(session)
            candidates=[]
            for context in [None]+list(contexts):
                try:
                    candidate=await evaluate("({title:document.title,text:document.body?document.body.innerText:'',metrics:[...document.querySelectorAll('[data-testid=stMetric]')].map(x=>x.innerText)})",context)
                    if isinstance(candidate,dict):candidates.append((context,candidate))
                except RuntimeError:
                    continue
            if candidates:
                active,snapshot=max(candidates,key=lambda item:(RELEASE in item[1].get('text',''),len(item[1].get('text',''))))
            text=snapshot.get('text','')
            ready=RELEASE in text and all(any(label in metric and number in metric for metric in snapshot['metrics'])
                for label,number in [('Simulated customer reactions','260'),('Contextual news sources','32'),('Accepted model classifications','220'),('Rejected model classifications','40')])
            if ready or (observe_only and len(text)>150) or time.monotonic()>=deadline:break
            # Public Community Cloud wake-up is a normal authorised app action, not authentication.
            if 'gone to sleep' in text.lower():
                try:
                    await evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(x=>/yes, get this app back up/i.test(x.innerText));if(b)b.click();return !!b})()")
                except RuntimeError:
                    active=None
            await asyncio.sleep(2)
        snapshot['overview_verified']=bool(ready)
        if ready and not observe_only and (story or 'Strategic Question' in snapshot.get('text','')):
            snapshot['sections_verified'] = []
            snapshot['layout_checks'] = []
            async def screenshot(name):
                capture = await call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
                suffix = 'mobile' if mobile else 'desktop'
                (ROOT/f'benchmarks/story_{suffix}_{name}.png').write_bytes(base64.b64decode(capture['data']))
            await screenshot('landing')
            sections = ['Strategic Question','Evidence & Methodology','Analysis',
                        'Insights & Synthesis','Research Appendix']
            for index, label in enumerate(sections):
                clicked = await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==="+json.dumps(label)+");if(b)b.click();return !!b})()")
                await asyncio.sleep(1)
                visible = await evaluate("[...document.querySelectorAll('[role=tabpanel]')].filter(x=>!x.hidden).map(x=>x.innerText).join('\\n')")
                if clicked and visible: snapshot['sections_verified'].append(label)
                if index == 2:
                    snapshot['real_media_verified'] = 'Real Media Insights' in visible and '14/32' in visible and '0/32 resolved human reviews' in visible
                    await screenshot('media')
                    await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Simulated Customer Reaction Analysis');b.click()})()")
                    await asyncio.sleep(1)
                    await evaluate("[...document.querySelectorAll('.story-card')].find(x=>x.innerText.startsWith('Reaction A')).scrollIntoView({block:'start'})")
                    await screenshot('mechanisms')
                    await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Customer voice');b.click()})()")
                    await asyncio.sleep(1)
                    voice = await evaluate('document.body.innerText')
                    snapshot['customer_voice_verified'] = 'Showing 260/260 simulations' in voice
                    await screenshot('voice')
                    await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Mechanisms & charts');b.click()})()")
                    await asyncio.sleep(2)
                    snapshot['charts_rendered'] = await evaluate("[...document.querySelectorAll('[data-testid=stVegaLiteChart] canvas,[data-testid=stVegaLiteChart] svg')].filter(x=>x.getBoundingClientRect().width>0).length")
                    await evaluate("document.querySelector('[data-testid=stVegaLiteChart]').scrollIntoView({block:'center'})")
                    await screenshot('charts')
                if index == 4:
                    await evaluate("(()=>{const b=[...document.querySelectorAll('summary')].find(x=>x.innerText.includes('50 AI-assisted review proposals'));if(b)b.click()})()")
                    await asyncio.sleep(.5)
                layout = await evaluate("({viewport:innerWidth,body:document.documentElement.scrollWidth,processColumns:document.querySelector('.story-process')?getComputedStyle(document.querySelector('.story-process')).gridTemplateColumns:null,errors:[...document.querySelectorAll('[data-testid=stException]')].map(x=>x.innerText)})")
                snapshot['layout_checks'].append({'section':label, **layout})
                await evaluate("document.querySelector('[data-testid=stMain]').scrollTo(0,0)")
                await screenshot(str(index))
            snapshot['review_proposals_verified'] = '50-case AI-assisted error review' in await evaluate('document.body.innerText')
        elif ready and not observe_only:
            await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Customer voice');if(b)b.click();return !!b})()")
            await asyncio.sleep(2)
            voice=await evaluate('document.body.innerText')
            snapshot['customer_voice_verified']='Showing 260/260 simulations' in voice
            await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Model evaluation');if(b)b.click();return !!b})()")
            await asyncio.sleep(2)
            evaluation=await evaluate('document.body.innerText')
            snapshot['review_proposals_verified']='50-case AI-assisted error review' in evaluation
            snapshot['evaluation_text']=evaluation
            await evaluate("(()=>{const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='Contagion analytics');if(b)b.click();return !!b})()")
            await asyncio.sleep(1)
        screenshot=await call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        (ROOT/'benchmarks/public_demo_render.png').write_bytes(base64.b64decode(screenshot['data']))
        try:await call('Browser.close')
        except (Exception, asyncio.CancelledError):pass
        return snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default=URL)
    parser.add_argument('--timeout',type=int,default=90)
    parser.add_argument('--observe-only',action='store_true')
    parser.add_argument('--story',action='store_true',help='Inspect the five-section strategic narrative')
    parser.add_argument('--mobile',action='store_true',help='Inspect a 390px mobile viewport')
    args=parser.parse_args()
    browsers=[Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
              Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')]
    browser=next((p for p in browsers if p.exists()),None)
    if browser is None:raise RuntimeError('No installed Chrome/Edge; nothing downloaded.')
    (ROOT/'benchmarks').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rayban_public_browser_',ignore_cleanup_errors=True) as directory:
        profile=Path(directory)
        process=subprocess.Popen([str(browser),'--headless=new','--disable-gpu','--no-first-run',
            '--no-default-browser-check','--disable-background-networking','--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0','--window-size=1440,1100','--user-data-dir='+str(profile),args.url],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline=time.monotonic()+25
            while not (profile/'DevToolsActivePort').exists():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Headless browser did not start.')
                time.sleep(.2)
            port=(profile/'DevToolsActivePort').read_text().splitlines()[0]
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list',timeout=5) as response:
                targets=json.load(response)
            target=next(t for t in targets if t['type']=='page')
            snapshot=asyncio.run(inspect(target['webSocketDebuggerUrl'],args.timeout,args.observe_only,
                                       story=args.story,mobile=args.mobile))
            snapshot['url']=args.url
            destination = ('story_mobile_verification.json' if args.mobile else 'story_desktop_verification.json') if args.story else 'public_demo_verification.json'
            (ROOT/'benchmarks'/destination).write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:snapshot.get(key) for key in ('url','title','overview_verified','customer_voice_verified','review_proposals_verified')}))
            if args.story:
                if len(snapshot.get('sections_verified',[])) != 5 or snapshot.get('charts_rendered') != 5:
                    raise SystemExit('Narrative sections or charts did not render.')
                if not snapshot.get('real_media_verified'):
                    raise SystemExit('Real media counts or provisional review status did not render.')
                if any(row['errors'] or row['body']>row['viewport'] for row in snapshot.get('layout_checks',[])):
                    raise SystemExit('Layout overflow or app exception detected.')
            if not args.observe_only and not all(snapshot.get(k) for k in ('overview_verified','customer_voice_verified','review_proposals_verified')):
                raise SystemExit('Live rendered results not verified; inspect ignored verification snapshot.')
        finally:
            if process.poll() is None:
                process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':main()
