"""Compile only cross-checked source facts; unresolved savings remain unknown."""
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import re
from pathlib import Path

from contracts import SCOPE, SHOP, require
from financial_contracts import amount, bill_fact, check_pages
from app.domain.member_consumption import BillLine, ConsumptionBill
from app.services.member_financial_import import FinancialBatch, SourceBalance, SourceBill, packet_sha256

TZ = timezone(timedelta(hours=8))
FILES = ('collection-pass1.json','collection-pass2.json','ledger-pass1.json','payments-pass1.json')

def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def source_time(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?",value),"source_time_invalid")
    return datetime.fromisoformat(value).replace(tzinfo=TZ)

def personal_rows(collection):
    require(collection['schema']=='source-member-finance-observation@1' and collection['scope']==SCOPE and
            collection['status']=='collected_unverified' and collection['business_writes']==0,"source_collection_unverified")
    check_pages(collection['card_pages'],collection['total_cards'],15)
    require(len(collection['cards'])==collection['total_cards'],"source_cards_incomplete")
    cards={c['card_number']:c for c in collection['cards']}
    require(len(cards)==len(collection['cards']),"source_duplicate_card")
    require(set(cards)=={c for p in collection['card_pages'] for c in p['rows']},"source_card_pages_mismatch")
    result={}
    for phone,history in collection['histories'].items():
        for row in check_pages(history['pages'],history['total'],10):
            require(row['bill_no'] not in result,"source_bill_owner_ambiguous")
            result[row['bill_no']]=(phone,row)
    require(set(collection['histories'])=={c['phone'] for c in cards.values()},"source_member_history_missing")
    return cards,result

def comparable(row):
    detail={k:v for k,v in row['detail'].items() if k!='observed_title'}
    return dict(row,detail=detail)

def compile_packet(root, batch_key):
    root=Path(root)
    evidence={name:{'sha256':sha256((root/name).read_bytes()).hexdigest()} for name in FILES}
    one,two,ledger,payments=[json.loads((root/n).read_bytes()) for n in FILES]
    cards1,bills1=personal_rows(one); cards,bills=personal_rows(two)
    require(set(cards1)==set(cards) and set(bills1)==set(bills),"source_changed_between_passes")
    for raw,c in cards.items():
        require(all(c[k]==cards1[raw][k] for k in ('phone','card_name','store_name','source_balance_cents','source_bonus_cents')),
                "source_card_changed_between_passes")
        require(c['store_name']==SHOP and c['source_balance_cents']==c['list_balance_cents'],"source_balance_mismatch")
    for key,(phone,row) in bills.items():
        require(phone==bills1[key][0] and comparable(row)==comparable(bills1[key][1]),"source_bill_changed_between_passes")
        require(row['detail'].get('observed_title')=='单据详情-'+key,"source_bill_title_unproven")
    require(ledger['schema']=='source-ledger-observation@1' and ledger['status']=='collected_unverified' and
            ledger['shop_id']==1581453 and ledger['business_writes']==0,"ledger_unverified")
    require(payments['schema']=='source-payment-observation@1' and payments['status']=='collected_unverified' and
            payments['shop_id']==1581453 and payments['business_writes']==0,"payment_unverified")
    for dataset,size in ((ledger,10),(payments,15)):
        pages=dataset['pages'];total=dataset['source_total']
        require(len(pages)==max(1,(total+size-1)//size),"finance_page_count_mismatch")
        for number,page in enumerate(pages,1):
            require(page['number']==number and page['last']==(number==len(pages)) and
                    page['source_rows']==min(size,total-(number-1)*size),"finance_pages_incomplete")
    require(ledger['query_dates']==payments['query_dates'],"finance_date_scope_mismatch")
    versions={key:[] for key in bills}
    for page in ledger['pages']:
        for row in page['rows']:
            require(row['单号'] in versions,"ledger_unexpected_bill")
            versions[row['单号']].append(row)
    require(all(versions.values()),"ledger_missing_member_bill")
    source_sha=digest(evidence)
    observed=datetime.fromisoformat(two['observed_at'])
    balances=[]; normalized=[]
    report={'source_cards':len(cards),'source_customers':len(two['histories']),'source_bills':len(bills),
            'shared_or_unresolved_bills':0,'non_service_bills':0,'revision_conflicts':0,
            'visible_bills':0,'balance_snapshots':0,'verified_savings_bills':0,'business_writes':0}
    for raw,c in cards.items():
        if c['card_name']!='荷小悦会员卡':continue
        require(c['source_bonus_cents']==0,"nonzero_bonus_semantics_unproven")
        # List and detail agree on available balance; principal remains unknown.
        balances.append(SourceBalance(raw,c['phone'],datetime.fromisoformat(c['observed_at']),
            c['source_balance_cents'],None,0,'source/collection-pass2.json'))
    for key,(phone,row) in bills.items():
        fact=bill_fact(row,row['detail']); candidates=[c for c in cards.values() if c['phone']==phone]
        require(candidates,"source_card_owner_missing")
        if len(candidates)!=1 or fact['guest_count']!=1:
            report['shared_or_unresolved_bills']+=1;continue
        if {x.get('type') for x in row['items']}!={'项'}:
            report['non_service_bills']+=1;continue
        if len(versions[key])!=1:
            report['revision_conflicts']+=1;continue
        ledger_row=versions[key][0]
        require(ledger_row['消费门店']==SHOP and ledger_row['状态']=='正常单(已结账)',"ledger_bill_not_normal")
        require(amount(ledger_row['金额总计'])==fact['settled_total_cents'],"ledger_amount_mismatch")
        require(any(re.fullmatch(r'消费门店：\s*'+re.escape(SHOP),v) for v in row['detail']['scope_and_time']),"bill_shop_unproven")
        header=[v for v in row['detail']['financial_summary'] if v.startswith('消费总额：')]
        require(len(header)==1 and amount(header[0].replace('消费总额：','').strip())==fact['settled_total_cents'],"detail_amount_mismatch")
        lines=[]
        for number,x in enumerate(fact['lines'],1):
            qty=Decimal(x['quantity']) if x['quantity'] is not None else None
            # Only unit quantity makes display price and line total unambiguous.
            lines.append(BillLine(x['description'],qty,x['original_display_cents'] if qty==1 else None,
                                 x['selling_display_cents'] if qty==1 else None,line_order=number))
        originals=[x.store_price_cents for x in lines]; settled=[x.settled_cents for x in lines]
        if all(x is not None for x in settled):
            require(sum(settled)==fact['settled_total_cents'],"source_line_total_mismatch")
        total_original=sum(originals) if originals and all(x is not None for x in originals) else None
        bill=ConsumptionBill(key,digest({'personal':row,'ledger':ledger_row}),1,None,bill_type='service',
             bill_status='normal_settled',attribution_status='owned',refund_status='unknown',
             occurred_at=source_time(row['time']),settled_at=source_time(ledger_row['结账时间']),
             store_price_total_cents=total_original,settled_total_cents=fact['settled_total_cents'],lines=tuple(lines))
        normalized.append(SourceBill(candidates[0]['card_number'],phone,bill,'source/collection-pass2.json'))
    start,end=map(source_time,ledger['query_dates'])
    gaps={'unbounded_personal_history':True,'refund_linkage_unverified':True,'payment_allocation_unverified':True,
          'excluded_shared_or_unresolved':report['shared_or_unresolved_bills'],'excluded_revisions':report['revision_conflicts'],
          'scope':'verified_owned_service_subset'}
    packet=FinancialBatch(batch_key,source_sha,'0'*64,start,end,observed,
                         len(two['card_pages'])+sum(len(h['pages']) for h in two['histories'].values())+len(ledger['pages'])+len(payments['pages']),
                         True,gaps,'source-index.json',tuple(normalized),tuple(balances))
    packet=replace(packet,manifest_sha256=packet_sha256(packet))
    report.update(visible_bills=len(normalized),balance_snapshots=len(balances),manifest_sha256=packet.manifest_sha256,
                  source_snapshot_sha256=source_sha)
    return packet,evidence,report

def encode_packet(packet):
    def default(value):
        if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
        if isinstance(value,Decimal):return int(value) if value==int(value) else str(value)
        raise TypeError('packet_value_invalid')
    return json.dumps(asdict(packet),ensure_ascii=False,sort_keys=True,indent=2,default=default)+'\n'

def decode_packet(data):
    data=dict(data)
    for name in ('query_range_start','query_range_end','observed_at'):data[name]=datetime.fromisoformat(data[name])
    bills=[]
    for raw in data['bills']:
        raw=dict(raw);bill=dict(raw['bill'])
        for name in ('occurred_at','settled_at'):
            if bill[name] is not None:bill[name]=datetime.fromisoformat(bill[name])
        bill['lines']=tuple(BillLine(**dict(x,quantity=Decimal(str(x['quantity'])) if x['quantity'] is not None else None)) for x in bill['lines'])
        bill['linked_card_ids']=tuple(bill['linked_card_ids']);raw['bill']=ConsumptionBill(**bill);bills.append(SourceBill(**raw))
    data['bills']=tuple(bills)
    data['balances']=tuple(SourceBalance(**dict(x,observed_at=datetime.fromisoformat(x['observed_at']))) for x in data['balances'])
    return FinancialBatch(**data)
