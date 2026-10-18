"""Refresh the visualization without retraining or rerunning experiments."""
import argparse
import json
import gzip
import base64
from pathlib import Path


def build(folder):
    root=Path(__file__).resolve().parent
    data=json.loads((folder/'replay_data.json').read_text(encoding='utf-8'))
    motion=json.loads((folder/'replay_motion.json').read_text(encoding='utf-8'))
    packed=base64.b64encode(gzip.compress(json.dumps(dict(traces=data,motion=motion),separators=(',',':')).encode(),mtime=0)).decode()
    template=(root/'replay_template.html').read_text(encoding='utf-8')
    (folder/'replay.html').write_text(template.replace('/*PAYLOAD*/""',json.dumps(packed)),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'results')
    build(parser.parse_args().results)
