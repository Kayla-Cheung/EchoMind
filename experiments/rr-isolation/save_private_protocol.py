import json
from pathlib import Path
from rr_v05 import load_stimuli
from isolation_protocol import schedule,messages,digest,PARAMETERS,GRAMMAR_DIFF
ROOT=Path(__file__).resolve().parent
stim=load_stimuli(ROOT/'private_inputs/calm_rr_v42.json')
plans=[]
for cell in schedule(stim):
    enc=messages(stim,cell,'encoding');rat_template=messages(stim,cell,'rating','<ENCODING_RESPONSE_FROM_SAME_EPISODE>')
    plans.append({**cell,'encoding_prompt_hash':digest(enc),'rating_template_hash':digest(rat_template),
                  'rating_actual_prompt_hash':None,'encoding_messages':enc,'rating_template_messages':rat_template,'sent':False})
(ROOT/'private_exports/01_PROTOCOL.json').write_text(json.dumps({'parameters':PARAMETERS,'grammar_diff':GRAMMAR_DIFF,'plan':plans,'note':'All messages are unsent templates. No placeholder is a model response.'},indent=2,ensure_ascii=False),encoding='utf-8')
print('Saved 60 private unsent transcript templates and prompt hashes.')
