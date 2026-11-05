import subprocess,json
from pathlib import Path
import numpy as np
from scipy.io.wavfile import write
from scipy.ndimage import gaussian_filter1d
P=Path(__file__).resolve().parent;ROOT=P.parents[2];OUT=ROOT/'outputs/demo';SR=48000
grid=json.loads((P/'grid.json').read_text());shots=json.loads((P/'timeline.json').read_text());D=grid['duration'];N=round(D*SR)
def decode(path,filters=None,start=None,duration=None):
 a=['ffmpeg','-v','error'];
 if start is not None:a+=['-ss',str(start)]
 a+=['-i',str(path)]
 if duration:a+=['-t',str(duration)]
 if filters:a+=['-af',filters]
 a+=['-f','f32le','-ac','2','-ar',str(SR),'-']
 return np.frombuffer(subprocess.check_output(a),dtype=np.float32).reshape(-1,2).copy()
def add(dst,x,t,gain=1):
 k=round(t*SR);a=max(0,k);b=min(N,k+len(x));dst[a:b]+=x[a-k:b-k]*gain
voice=np.zeros((N,2),dtype=np.float32);activity=np.zeros(N,dtype=np.float32)
lines=json.loads((P/'voice.json').read_text())
for i,(t,text) in enumerate(lines):
 x=decode(P/f'narration-{i}.mp3','highpass=f=85,loudnorm=I=-18:TP=-5:LRA=9');add(voice,x,t)
 activity[max(0,int((t-.15)*SR)):min(N,int((t+len(x)/SR+.12)*SR))]=1
write(P/'voice-stem.wav',SR,voice)
# Keep the groove audible in gaps and gently duck beneath speech.
music=decode(P/'music.mp3','loudnorm=I=-19:TP=-6:LRA=8',grid['offset'],32*grid['bar'])
music=np.tile(music,(2,1))[:N]
# Smooth the ducking at 100Hz so it is fast and independent of sample rate.
activity_low=activity[::480];smooth=gaussian_filter1d(activity_low,10)
duck=np.interp(np.arange(N)/480,np.arange(len(smooth)),smooth)
music*=((1-duck*.66)*np.minimum(1,np.arange(N)/(.12*SR))*np.minimum(1,(N-np.arange(N))/(1.1*SR)))[:,None]
sfx=np.zeros_like(voice);kit=P.parent/'motion-graphics/skills/sound-effects/sfx/kit';samples={k:decode(kit/f'{k}.ogg') for k in ['whoosh','impact','click']}
cues=[]
for i,s in enumerate(shots):
 if i==0:continue
 t=s['start'];name='impact' if s['kind']=='g' else 'whoosh'
 ts=t if name=='impact' else t-.055
 add(sfx,samples[name],ts,.24 if name=='impact' else .14)
 cues.append({'time':round(ts,3),'effect':name,'action':shots[i]['title']})
for i in range(3):
 t=.24*i+.08;add(sfx,samples['click'],t,.13);cues.append({'time':t,'effect':'click','action':'3D application card arrives'})
for t in [3*grid['beat'],6*grid['beat']]:
 add(sfx,samples['impact'],t,.13);cues.append({'time':round(t,3),'effect':'impact','action':'Opening hook changes on beat'})
for i in [i for i,s in enumerate(shots) if s['kind']=='v']:
 t=shots[i]['start']+.32;add(sfx,samples['click'],t,.14);cues.append({'time':round(t,3),'effect':'click','action':'UI microcut settles'})
write(P/'music-stem.wav',SR,music);write(P/'sfx-stem.wav',SR,sfx);write(P/'mix.wav',SR,voice+music+sfx)
(P/'cues.json').write_text(json.dumps(sorted(cues,key=lambda c:c['time']),indent=2))
OUT.mkdir(exist_ok=True)
if (P/'silent.mp4').exists():
 subprocess.run(['ffmpeg','-v','error','-y','-i',str(P/'silent.mp4'),'-i',str(P/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af','loudnorm=I=-16:TP=-4.2:LRA=9','-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-t',str(D),'-movflags','+faststart',str(OUT/'offerletter-unslop.mp4')],check=True)
 print('EXPORTED',OUT/'offerletter-unslop.mp4',flush=True)
else:print('Audio mix ready',flush=True)

