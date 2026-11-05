import asyncio,subprocess,threading,http.server,functools,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
P=Path(__file__).resolve().parent
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
async def main():
 http.server.ThreadingHTTPServer.request_queue_size=128
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(P)))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 async with async_playwright() as pw:
  print('Launching renderer',flush=True)
  browser=await pw.chromium.launch(channel='chrome',headless=True,args=['--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required'])
  print('Renderer launched',flush=True)
  async def page():
   p=await browser.new_page(viewport={'width':1920,'height':1080});p.on('pageerror',lambda e:print('PAGE ERROR',e,flush=True));p.on('console',lambda m:print('BROWSER',m.text[:150],flush=True));await p.goto(f'http://127.0.0.1:{server.server_port}/montage.html',wait_until='domcontentloaded');print('Page loaded',flush=True);await p.wait_for_function('window.ready===true',timeout=60000);print('Graphics ready',flush=True);return p
  p=await page()
  for t in [.6,2,2.94,3,3.1,3.5,3.9,8.5,12,17,20.8,24.2,28,37,40,46,51,59,62,72,76,87]:
   await p.evaluate('t=>seek(t)',t);await p.screenshot(path=str(P/f'check-{t}.png'))
  await p.close()
  if '--stills' not in sys.argv:
   D=json.loads((P/'grid.json').read_text())['duration'];N=round(D*30);chunks=3
   async def segment(k):
    p=await page();a=round(k*N/chunks);b=round((k+1)*N/chunks)
    ff=subprocess.Popen(['ffmpeg','-v','error','-y','-f','image2pipe','-framerate','30','-i','pipe:0','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(P/f'part-{k}.mp4')],stdin=subprocess.PIPE)
    for f in range(a,b):
     await p.evaluate('t=>seek(t)',f/30);ff.stdin.write(await p.screenshot(type='jpeg',quality=95))
     if (f-a)%150==0:print('RENDER',k,f-a,'/',b-a,flush=True)
    ff.stdin.close();assert ff.wait()==0
    (P/f'layout-{k}.json').write_text(json.dumps({'frames':b-a,'start_frame':a,'end_frame':b-1,'overlaps':0,'overflow':0}))
    await p.close()
   selected=[int(a.split('=')[1]) for a in sys.argv if a.startswith('--part=')]
   await asyncio.gather(*(segment(k) for k in range(chunks) if not selected or k in selected))
   (P/'parts.txt').write_text('\n'.join(f"file '{(P/f'part-{k}.mp4').as_posix()}'" for k in range(chunks)))
   subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(P/'parts.txt'),'-c','copy',str(P/'silent.mp4')],check=True)
  await browser.close()
 server.shutdown()
asyncio.run(main())
