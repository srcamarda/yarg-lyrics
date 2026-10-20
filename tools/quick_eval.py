"""Avalia uma música (índice em gold_all.json) com o aligner de YL_ALIGNER. Só números."""
import sys, os, json, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import run
from yl import aligners
folders = json.load(open(os.path.join(ROOT, 'gold_all.json'), encoding='utf-8-sig'))
for i in map(int, sys.argv[1:]):
    t = time.time()
    r = run.process(folders[i], do_eval=True)
    e = r.get('eval', {})
    print(f"{aligners.name():10} [{i}] {r.get('lang')} {time.time()-t:5.1f}s  med={e.get('median_ms')} "
          f"<=100={e.get('within_100ms')} <=250={e.get('within_250ms')} >1s={e.get('over_1s')} bias={e.get('bias_ms')}", flush=True)
