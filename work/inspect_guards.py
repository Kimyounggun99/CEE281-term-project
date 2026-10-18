import sys
import json
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[1] / 'outputs' / 'traffic_project'
sys.path.insert(0, str(root))
from microscopic import run
from forecast import demand_rates

def trace(frame, event, arg):
    if frame.f_code.co_name != 'step' or not frame.f_code.co_filename.endswith('microscopic.py'):
        return None
    if event == 'line' and frame.f_lineno == 89:
        d = frame.f_locals
        j = d['j']
        print({k:d[k] for k in ('t','label','ch','cap')},
              {k:float(d[k][j]) for k in ('x','nx','speed','nv','acc')}, flush=True)
    return trace

c = json.loads((root/'config.json').read_text())
arrivals = np.random.default_rng(102).poisson(demand_rates(np.arange(c['duration_s']),c['duration_s'],'balanced',day=2)[:,:,None]*np.array(c['lane_demand_factors']))
sys.settrace(trace)
metrics, _ = run(arrivals,'fixed','balanced',102,c,None)
sys.settrace(None)
print(metrics['collision_guard_corrections'])
