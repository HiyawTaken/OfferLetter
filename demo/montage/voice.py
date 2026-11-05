import asyncio,json,sys,subprocess
from pathlib import Path
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'deps'))
import edge_tts
# Short spoken phrases, natural contractions and breathing room between ideas.
LINES=[
 (0.4,"You found the job. Now comes the same form. Again."),
 (7.95,"That's why we built OfferLetter."),
 (12.0,"Start with your education and work experience. What you did, where you worked, and when."),
 (21.8,"Then pick the roles you're looking for. That's what guides the search."),
 (28.0,"OfferLetter finds jobs and checks what they're actually asking for. A matching title is just the start."),
 (36.4,"Close match? You get to decide."),
 (41.6,"And this? That's a real application being filled in. Your contact details. Education. All that repeated typing."),
 (53.4,"A new question comes up? Answer it once. You choose when it's reused, even if it's just for this job."),
 (63.3,"Before anything goes out, check the details. Review your answers, including the sensitive ones."),
 (71.0,"Nothing gets submitted until you approve. You're still in control."),
 (79.1,"Less copy and paste. More time for your next move. That's OfferLetter.")
]
async def main():
 for i,(start,text) in enumerate(LINES):
  dest=P/f'narration-{i}.mp3'
  if not dest.exists():
   await edge_tts.Communicate(text,'en-US-AvaMultilingualNeural',rate='+2%',pitch='+0Hz').save(str(dest))
  d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(dest)]))
  print(i,start,round(d,2),text,flush=True)
 (P/'voice.json').write_text(json.dumps(LINES))
asyncio.run(main())
