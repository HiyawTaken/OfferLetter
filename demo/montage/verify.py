import json,subprocess,re
from pathlib import Path
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parent;ROOT=P.parents[2];OUT=ROOT/'outputs/demo';video=OUT/'offerletter-unslop.mp4'
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)]))
assert abs(float(info['format']['duration'])-90.49)<.12
v=next(s for s in info['streams'] if s['codec_type']=='video');assert (v['width'],v['height'])==(1920,1080)
assert abs(float(v['duration'])-90.49)<.12, 'Video must run through the entire extended timeline'
subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
levels=subprocess.run(['ffmpeg','-hide_banner','-i',str(video),'-af','loudnorm=I=-16:TP=-4:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
stats=json.loads(re.search(r'\{\s*"input_i".*?\}',levels,re.S).group())
assert float(stats['input_tp'])<-3.0
assert -18<float(stats['input_i'])<-14
layout=[json.loads((P/f'layout-{k}.json').read_text()) for k in range(3)]
assert sum(x['frames'] for x in layout)==2715
assert sum(x['overlaps']+x['overflow'] for x in layout)==0
report={'duration':info['format']['duration'],'video_duration':v['duration'],'size':info['format']['size'],'resolution':[v['width'],v['height']],'frame_rate':v['r_frame_rate'],'audio':stats,'full_decode':'passed','layout_frames_checked':2715,'layout_failures':0}
(P/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
shots=json.loads((P/'timeline.json').read_text());times=[s['start']+min(s['duration']*.6,2) for s in shots]
sheet=Image.new('RGB',(1920,((len(times)+3)//4)*300),'#101913');d=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
 f=P/f'final-shot-{i}.png'
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(f)],check=True)
 im=Image.open(f).resize((480,270));x=i%4*480;y=i//4*300;sheet.paste(im,(x,y));d.text((x+10,y+278),f'{t:.1f}s / {shots[i]["title"]}',fill='white')
sheet.save(P/'final-contact.jpg')
for t in [1,2.5,2.94,3,3.1,3.5,3.9,56,72,87]:
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(P/f'final-{t}.png')],check=True)
