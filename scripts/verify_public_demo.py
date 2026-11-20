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
RELEASE='hec-review-2026-11-20-v1'


async def inspect(socket_url, timeout, observe_only):
    async with websockets.connect(socket_url,max_size=12_000_000,proxy=None) as socket:
        sequence=0
        async def call(method,params=None):
            nonlocal sequence
            sequence+=1; request_id=sequence
            await socket.send(json.dumps({'id':request_id,'method':method,'params':params or {}}))
            while True:
                message=json.loads(await asyncio.wait_for(socket.recv(),timeout=15))
                if message.get('id')==request_id:
                    if message.get('error'):raise RuntimeError(message['error'])
                    return message.get('result',{})
        async def evaluate(expression):
            result=await call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
            if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
            return result.get('result',{}).get('value')
        deadline=time.monotonic()+timeout
        snapshot={}
        while True:
            snapshot=await evaluate("({url:location.href,title:document.title,text:document.body.innerText,metrics:[...document.querySelectorAll('[data-testid=stMetric]')].map(x=>x.innerText)})")
            text=snapshot.get('text','')
            ready=RELEASE in text and all(any(label in metric and number in metric for metric in snapshot['metrics'])
                for label,number in [('Simulated customer reactions','260'),('Contextual news sources','32'),('Accepted model classifications','220'),('Rejected model classifications','40')])
            if ready or (observe_only and len(text)>150) or time.monotonic()>=deadline:break
            # Public Community Cloud wake-up is a normal authorised app action, not authentication.
            await evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(x=>/yes, get this app back up/i.test(x.innerText));if(b)b.click();return !!b})()")
            await asyncio.sleep(2)
        snapshot['overview_verified']=bool(ready)
        if ready and not observe_only:
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
            snapshot=asyncio.run(inspect(target['webSocketDebuggerUrl'],args.timeout,args.observe_only))
            (ROOT/'benchmarks/public_demo_verification.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:snapshot.get(key) for key in ('url','title','overview_verified','customer_voice_verified','review_proposals_verified')}))
            if not args.observe_only and not all(snapshot.get(k) for k in ('overview_verified','customer_voice_verified','review_proposals_verified')):
                raise SystemExit('Live rendered results not verified; inspect ignored verification snapshot.')
        finally:
            if process.poll() is None:
                process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


if __name__=='__main__':main()
