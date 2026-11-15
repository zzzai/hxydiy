"""Transaction-local protection of all pre-existing public rows."""
from collections import Counter
from hashlib import sha256
import json
import re
from sqlalchemy import text

APPEND_TABLES = {'membership_consumption_batches','membership_consumption_bills',
                 'membership_consumption_lines','membership_balance_snapshots'}

def tables(db):
    names=list(db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")))
    if not names or not all(re.fullmatch(r'[a-z][a-z0-9_]*',n) for n in names):raise ValueError('unexpected_table_schema')
    if not APPEND_TABLES.issubset(names):raise ValueError('finance_tables_missing')
    return names

def snapshot(db, names=None):
    names=tables(db) if names is None else names
    return {name:list(db.scalars(text('SELECT md5(row_to_json(t)::text) AS h FROM public."'+name+'" t ORDER BY h'))) for name in names}

def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Protection:
    def __init__(self,baseline,expected=None):self.baseline=baseline;self.result=None;self.expected=expected
    def before(self,db):
        if db.bind.dialect.name!='postgresql':raise ValueError('production_protection_requires_postgresql')
        db.execute(text("SET LOCAL lock_timeout='5s'"));db.execute(text("SET LOCAL statement_timeout='30s'"))
        names=tables(db)
        # Short transaction lock: reads continue; concurrent business writes wait.
        db.execute(text('LOCK TABLE '+', '.join('public."'+n+'"' for n in names)+' IN SHARE MODE'))
        current=snapshot(db,names)
        if current!=self.baseline:raise ValueError('protection_baseline_changed')
        self.names=names
    def after(self,db):
        current=snapshot(db,self.names)
        for name,old in self.baseline.items():
            if name not in APPEND_TABLES:
                if current[name]!=old:raise ValueError('protected_table_changed')
            elif Counter(old)-Counter(current[name]):raise ValueError('prior_finance_row_changed')
        if self.expected is not None:
            for name in APPEND_TABLES:
                if len(current[name])-len(self.baseline[name])!=self.expected[name]:raise ValueError("append_count_mismatch")
        self.result={'old_tables_unchanged':True,'old_finance_rows_unchanged':True,
                     'before_sha256':fingerprint(self.baseline),'after_sha256':fingerprint(current),
                     'counts':{n:len(v) for n,v in current.items()}}
