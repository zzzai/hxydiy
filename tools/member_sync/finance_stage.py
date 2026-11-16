"""Compile immutable source evidence inside the existing application runtime, without DB access."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--batch-key',required=True)
    args=parser.parse_args();root=args.root.resolve();os.umask(0o077)
    if root!=Path(__file__).resolve().parent or root.stat().st_mode&0o077:raise ValueError('private_stage_invalid')
    import app.services
    app.services.__path__.insert(0,str(root))
    from finance_packet import compile_packet,encode_packet
    packet,index,summary=compile_packet(root/'source',args.batch_key)
    for name,value in [('packet.json',encode_packet(packet)),('source-index.json',json.dumps(index,sort_keys=True)),('source-summary.json',json.dumps(summary,sort_keys=True))]:
        with (root/name).open('x',encoding='utf-8') as stream:stream.write(value)
    print(json.dumps(summary))

if __name__=='__main__':main()
