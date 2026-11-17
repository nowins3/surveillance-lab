"""Optional end-to-end check. Requires Playwright and a Chromium executable.
Run from project root: python tests/browser_smoke.py
Uses an isolated temporary server on port 8765. Does not require internet.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]

async def main():
    process=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--host','127.0.0.1','--port','8765'],stdout=subprocess.DEVNULL)
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'),headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
            manager_context=await browser.new_context(viewport={'width':1440,'height':1050},permissions=['camera'])
            participant_context=await browser.new_context(viewport={'width':390,'height':844})
            manager=await manager_context.new_page();participant=await participant_context.new_page()
            errors=[]
            for page in (manager,participant):page.on('pageerror',lambda error:errors.append(str(error)))
            for _ in range(30):
                try:await manager.goto('http://localhost:8765');break
                except Exception:await asyncio.sleep(.2)
            await manager.locator('#title').fill('Surveillance: a collective experiment')
            await manager.get_by_role('button',name='Create a session').click()
            await manager.locator('#roomCode').wait_for()
            code=await manager.locator('#roomCode').inner_text()
            await manager.wait_for_function("document.querySelector('#sourceLabel').textContent==='Camera'")
            await participant.goto('http://localhost:8765/?room='+code)
            await participant.locator('#nickname').fill('Observer 01')
            await participant.locator('.consent input').check()
            await participant.get_by_role('button',name='Join session').click()
            await participant.locator('#sessionTitle').wait_for()
            await manager.get_by_role('button',name='Start demo scene').click()
            await participant.wait_for_function("!document.querySelector('#feed').hidden")
            await participant.wait_for_function("document.querySelector('#observationTitle').textContent.includes('simulated')")
            await manager.locator('[data-scenario="presence"]').click()
            await participant.locator('[data-choice="1"]').click()
            await participant.locator('.choice.selected').wait_for()
            assert await participant.locator('.result-track').count()==0,'Participant saw early counts'
            await manager.locator('#revealRound').click()
            await participant.get_by_text('OPEN THE DISCUSSION').wait_for()
            assert '1 response' in await participant.locator('.round-footer').inner_text()
            screenshot_dir=Path(tempfile.mkdtemp(prefix='surveillance-preview-'))
            await manager.screenshot(path=str(screenshot_dir/'manager.png'),full_page=True)
            await participant.screenshot(path=str(screenshot_dir/'participant.png'),full_page=True)
            print('Browser screenshots:',screenshot_dir)
            # Reload restores the participant credential without creating a duplicate participant.
            await participant.reload()
            await participant.locator('#sessionTitle').wait_for()
            assert await participant.locator('#participantCount').inner_text()=='1'
            await manager.get_by_role('button',name='Share camera').click()
            await manager.wait_for_function("document.querySelector('#sourceLabel').textContent==='Camera'")
            await participant.wait_for_function("document.querySelector('#sourceLabel').textContent==='Camera'")
            assert not await participant.locator('#feed').is_hidden()
            await manager.get_by_role('button',name='Stop broadcast').click()
            await participant.wait_for_function("document.querySelector('#feed').hidden")
            # Custom scenario round trip.
            await manager.locator('#toggleCustom').click()
            form=manager.locator('#customForm')
            for key,value in {'title':'A new context','observation':'A staged event','question':'What would you do?','options':'Wait\nAsk for context','reveal':'Different contexts change decisions.'}.items():
                await form.locator(f'[name="{key}"]').fill(value)
            await form.get_by_role('button',name='Save scenario').click()
            await manager.get_by_role('heading',name='A new context').wait_for()
            # Start a new round and disconnect/reconnect the participant event stream.
            await manager.locator('.scenario-row').last.get_by_role('button').click()
            await participant.locator('[data-choice="0"]').wait_for()
            await participant_context.set_offline(True)
            await asyncio.sleep(.5)
            await participant_context.set_offline(False)
            await participant.wait_for_function("document.querySelector('#connection').textContent==='CONNECTED'")
            await participant.locator('[data-choice="0"]').click()
            await participant.locator('.choice.selected').wait_for()
            manager.once('dialog',lambda dialog:dialog.accept())
            await manager.locator('#endSession').click()
            await participant.locator('#endedBanner').wait_for()
            assert not errors,errors
            await browser.close()
            print('PASS: create/join, demo video, hidden results, voting/reveal, credential restore, fake camera, stop, custom scenario, reconnect, end; no browser JS errors.')
    finally:
        process.terminate();process.wait(timeout=10)

if __name__=='__main__':asyncio.run(main())
