"""Synthetic source observations exercise unknowns, identity and revision exclusion."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[2]/'hxy-server')]
from contracts import SCOPE,SHOP,Stop
from finance_packet import compile_packet,encode_packet,decode_packet
from app.services.member_financial_import import packet_sha256
from app.domain.member_consumption import compute_bill_savings

@pytest.fixture
def evidence(tmp_path):
    card={'card_number':' 00001','phone':'13900000001','card_name':'荷小悦会员卡','store_name':SHOP,
          'source_balance_cents':9000,'source_bonus_cents':0,'list_balance_cents':9000,'observed_at':'2026-11-15T01:00:00+00:00'}
    bill={'bill_no':'SYN-01','time':'2026-11-14 10:00','payment':'￥79','shop':SHOP,
          'items':[{'type':'项','name':'Synthetic','quantity':'×1','settled':'¥79','original':'原价¥119'}],
          'detail':{'bill_no':'SYN-01','observed_title':'单据详情-SYN-01','scope_and_time':['消费门店：'+SHOP,'客流：1'],
                    'financial_summary':['消费总额： ￥79'],'refund_status':'unknown','source_current_status':'unknown'}}
    collection={'schema':'source-member-finance-observation@1','scope':SCOPE,'status':'collected_unverified',
                'business_writes':0,'total_cards':1,'observed_at':'2026-11-15T01:01:00+00:00','cards':[card],
                'card_pages':[{'number':1,'rows':[' 00001'],'last':True}],
                'histories':{'13900000001':{'total':1,'pages':[{'number':1,'rows':[bill],'last':True}]}}}
    dates=['2026-01-01 00:00','2026-11-16 09:00']
    ledger={'schema':'source-ledger-observation@1','shop_id':1581453,'business_writes':0,'status':'collected_unverified',
            'query_dates':dates,'source_total':1,'pages':[{'number':1,'last':True,'source_rows':1,
            'rows':[{'单号':'SYN-01','消费门店':SHOP,'状态':'正常单(已结账)','金额总计':'￥79','结账时间':'2026-11-14 10:00:00'}]}]}
    payments={'schema':'source-payment-observation@1','shop_id':1581453,'business_writes':0,'status':'collected_unverified',
              'query_dates':dates,'source_total':0,'pages':[{'number':1,'last':True,'source_rows':0,'rows':[]}]}
    values={'collection-pass1.json':deepcopy(collection),'collection-pass2.json':collection,'ledger-pass1.json':ledger,'payments-pass1.json':payments}
    def write():
        for name,value in values.items():(tmp_path/name).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return compile_packet(tmp_path,'synthetic-finance')
    return values,write

def test_compiler_preserves_unknown_refund_and_exact_balance(evidence):
    _,write=evidence;p,_,report=write()
    assert p.balances[0].card_number==' 00001' and p.balances[0].total_cents==9000
    assert p.balances[0].principal_cents is None
    assert p.bills[0].bill.refund_status=='unknown' and p.bills[0].bill.settled_total_cents==7900
    assert compute_bill_savings(p.bills[0].bill).savings_cents is None
    assert report['verified_savings_bills']==0 and report['visible_bills']==1
    restored=decode_packet(json.loads(encode_packet(p)))
    assert restored==p and packet_sha256(restored)==p.manifest_sha256

@pytest.mark.parametrize('change',['phone','balance','title','page','amount','bonus'])
def test_incomplete_or_conflicting_evidence_blocks(evidence,change):
    values,write=evidence;c=values['collection-pass2.json']
    if change=='phone':c['cards'][0]['phone']='13900000002'
    if change=='balance':c['cards'][0]['list_balance_cents']=8000
    if change=='title':c['histories']['13900000001']['pages'][0]['rows'][0]['detail']['observed_title']='单据详情-WRONG'
    if change=='page':c['card_pages'][0]['last']=False
    if change=='amount':values['ledger-pass1.json']['pages'][0]['rows'][0]['金额总计']='￥80'
    if change=='bonus':
        for name in ('collection-pass1.json','collection-pass2.json'):values[name]['cards'][0]['source_bonus_cents']=100
    with pytest.raises(Stop):write()

def test_revisions_are_excluded_without_picking_latest(evidence):
    values,write=evidence;l=values['ledger-pass1.json'];old=dict(l['pages'][0]['rows'][0],状态='已撤单(已重录)')
    l['pages'][0]['rows'].append(old);l['source_total']=2;l['pages'][0]['source_rows']=2
    p,_,report=write();assert p.bills==() and report['revision_conflicts']==1

def test_shared_bill_never_assigned_to_first_owner(evidence):
    values,write=evidence
    for name in ('collection-pass1.json','collection-pass2.json'):
        values[name]['histories']['13900000001']['pages'][0]['rows'][0]['detail']['scope_and_time'][1]='客流：2'
    p,_,report=write();assert p.bills==() and report['shared_or_unresolved_bills']==1
