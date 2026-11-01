"""Exercise the full application over HTTP using new synthetic actors only."""
import hashlib,json,uuid
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from sqlalchemy import inspect,text
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.db.session import engine,SessionLocal
from app.models import Staff,Technician
from app.api.admin import create_staff_token

url=make_url(settings.database_url)
assert settings.environment=='test' and url.host=='learning-postgres-v8' and url.database=='learning_test'
proof=Path('/tmp/learning-formal-http-before.json')
assert not proof.exists(), 'Do not replay a completed acceptance run'
def snapshot():
    with engine.connect() as con:
        assert con.execute(text("select count(*) from stores where store_code in ('learning-demo-1','learning-demo-2')")).scalar()==2
        return {table:dict(Counter(hashlib.sha256(v.encode()).hexdigest() for v in con.execute(text('SELECT row_to_json(t)::text FROM '+engine.dialect.identifier_preparer.quote(table)+' t')).scalars())) for table in inspect(engine).get_table_names()}
proof.write_text(json.dumps(snapshot()))
with SessionLocal() as db:
    assert not db.get(Staff,9202)
    db.add_all([Technician(id=9202,store_id=1,code='formal-a',name='联调技师（合成）',status='available'),Technician(id=9203,store_id=2,code='formal-other',name='异店联调（合成）',status='available')]);db.flush()
    db.add_all([Staff(id=9201,username='formal-manager',role='manager',store_id=1,name='联调店长（合成）',password_hash='unused'),Staff(id=9202,username='formal-a',role='technician',store_id=1,technician_id=9202,name='联调技师（合成）',password_hash='unused'),Staff(id=9203,username='formal-other',role='technician',store_id=2,technician_id=9203,name='异店联调（合成）',password_hash='unused'),Staff(id=9204,username='formal-other-manager',role='manager',store_id=2,name='异店店长（合成）',password_hash='unused')]);db.commit()
tokens={id:create_staff_token(id,'manager' if id in [9201,9204] else 'technician') for id in [9201,9202,9203,9204]}
requests=0
checks=[]
def call(path,who=9202,body=None,status=200):
    global requests
    requests+=1
    headers={'Content-Type':'application/json'}
    if who:headers['Authorization']='Bearer '+tokens[who]
    try:
        with urlopen(Request('http://127.0.0.1:8011/api/v1/staff-learning'+path,headers=headers,data=json.dumps(body).encode() if body is not None else None),timeout=15) as response:
            code=response.status;data=json.load(response)
            assert response.headers['Cache-Control'].find('no-store')>=0
    except HTTPError as err:code=err.code;data=json.load(err)
    assert code==status,(path,code,status,data)
    return data
course=json.loads(Path('/workspace/content/staff-learning/culture-hxy-20260908-v2-pilot.json').read_text())[0]
call('/bootstrap',None,status=401)
call('/bootstrap?store_id=2',status=422)
assert call('/status')['enabled']
body={'staff_id':9202,'course_id':course['id'],'course_version':course['version'],'request_id':'formal-assign-20261030'}
call('/assignments',9202,body,403)
call('/assignments',9204,body,404)
snap=call('/assignments',9201,body)
item=next(a for a in snap['assignments'] if a['staffId']==9202)
assert next(a for a in call('/assignments',9201,body)['assignments'] if a['staffId']==9202)['id']==item['id']
checks.append('manager_assignment_readback_and_replay')
path='/assignments/'+item['id']+'/actions'
def current():return next(a for a in call('/bootstrap')['assignments'] if a['id']==item['id'])
answers={q['id']:q['answer'] for q in course['questions']}
for who in [9203,9204]:
    call(path,who,{'kind':'follow_up' if who==9204 else 'mark_section','request_id':'formal-denied-'+str(who),'expected_revision':0,**({'note':'Synthetic'} if who==9204 else {'section_id':course['sections'][0]['id']})},404)
call(path,9201,{'kind':'submit','request_id':'formal-no-proxy','expected_revision':0,'answers':answers},403)
call(path,9202,{'kind':'submit','request_id':'formal-read-required','expected_revision':0,'answers':answers},422)
call(path,9202,{'kind':'follow_up','request_id':'formal-no-coach','expected_revision':0,'note':'Synthetic'},403)
checks.append('cross_store_cross_actor_proxy_and_premature_submit_rejected')
for index,section in enumerate(course['sections']):
    body={'kind':'mark_section','request_id':'formal-read-'+str(index),'expected_revision':current()['revision'],'section_id':section['id']}
    call(path,body=body);revision=current()['revision'];call(path,body=body);assert current()['revision']==revision
assert len(current()['sectionsRead'])==3
snap=call('/bootstrap');assert all(a['staffId']==9202 for a in snap['assignments'])
assert all('answer' not in q and 'explanation' not in q for c in snap['courses'] for q in c['questions'])
checks.append('progress_readback_repeat_click_and_answers_hidden')
wrong={**answers,course['questions'][0]['id']:(course['questions'][0]['answer']+1)%3}
body={'kind':'submit','request_id':'formal-submit-first','expected_revision':current()['revision'],'answers':wrong}
call(path,body=body);call(path,body=body);saved=current();assert len(saved['attempts'])==1 and saved['attempts'][0]['correct']==2
call(path,body={**body,'answers':answers},status=409)
assert saved['attempts'][0]['review'][0]['explanation']==course['questions'][0]['explanation']
checks.append('server_grading_wrong_review_and_idempotency_conflict')
body={'kind':'follow_up','request_id':'formal-coach-first','expected_revision':saved['revision'],'note':'合成联调：先听顾客反馈，减少打扰，服务后再观察改进。'}
call(path,9201,body);call(path,9201,body);assert len(current()['followUps'])==1
call(path,body={'kind':'submit','request_id':'formal-stale-attempt','expected_revision':saved['revision'],'answers':answers},status=409)
body={'kind':'submit','request_id':'formal-submit-second','expected_revision':current()['revision'],'answers':answers}
call(path,body=body);call(path,body=body);saved=current()
assert [a['correct'] for a in saved['attempts']]==[2,3] and len(saved['followUps'])==1
checks.append('coaching_visible_retake_append_only_and_stale_revision_rejected')
before=json.loads(proof.read_text());after=snapshot();assert all(not(Counter(rows)-Counter(after[t])) for t,rows in before.items())
checks.append('every_previous_row_preserved')
result={'passed':True,'application':'app.main:app','transport':'HTTP','database':'isolated PostgreSQL','checks':checks,'requests':requests,'tables_protected':len(before),'production_touched':False}
Path('/tmp/learning-formal-http-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
