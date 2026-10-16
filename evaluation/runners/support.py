import argparse
import asyncio
from collections import Counter
from datetime import date,datetime,timezone
import hashlib
import json
from pathlib import Path
import uuid

from support_assistant.config import Settings
from support_assistant.adapters.groq.client import GroqClient
from support_assistant.adapters.cache.redis_cache import RedisClassifierCache
from support_assistant.routing.classifier import Classifier
from support_assistant.domain.conversation import Session,Turn
from support_assistant.domain.safety import ApprovalAuthority
from support_assistant.domain.evidence import InputDecision,SupportDecision
from support_assistant.rag.documents import load_documents
from support_assistant.rag.grounding import read_prompt
from support_assistant.safety.regex_guard import RegexGuard
from support_assistant.safety.authorization import authorize_order
from support_assistant.adapters.persistence.fixture_orders import FixtureOrders

ROOT=Path(__file__).resolve().parents[2]

def cases(name):return [json.loads(x) for x in (ROOT/'evaluation/datasets'/name).read_text().splitlines()]

def binary_metrics(rows,positive_expected,positive_actual):
    tp=sum(bool(r[positive_expected]) and bool(r[positive_actual]) for r in rows)
    fn=sum(bool(r[positive_expected]) and not bool(r[positive_actual]) for r in rows)
    fp=sum(not bool(r[positive_expected]) and bool(r[positive_actual]) for r in rows)
    tn=sum(not bool(r[positive_expected]) and not bool(r[positive_actual]) for r in rows)
    return {"true_positive":tp,"false_negative":fn,"false_positive":fp,"true_negative":tn,
        "recall":tp/(tp+fn) if tp+fn else None,"false_positive_rate":fp/(fp+tn) if fp+tn else None}

async def run(args):
    from redis.asyncio import Redis
    settings=Settings.from_env()
    prefix=settings.prefix+':eval:'+uuid.uuid4().hex
    redis=Redis.from_url(settings.redis_url,decode_responses=True)
    llm=GroqClient(settings.groq_key,settings.groq_model,settings.provider_timeout)
    cache=RedisClassifierCache(redis,prefix)
    classifier=Classifier(llm,cache)
    authority=ApprovalAuthority(300)
    session=Session(session_id='eval-session',customer_id='customer-a')
    result={"mode":"live_groq","split":"development_seed","model":settings.groq_model,
        "created_at":datetime.now(timezone.utc).isoformat(),"suites":{},"errors":[]}
    suites=['routing','ambiguity','input','output','tools','cache'] if args.suite=='all' else [args.suite]
    try:
        await redis.ping()
        for suite in suites:
            rows=[]
            if suite in ['routing','ambiguity']:
                for case in cases('routing.jsonl' if suite=='routing' else 'routing_ambiguity.jsonl'):
                    try:
                        route=await classifier.classify(authority._issue(session,Turn(turn_id=case['id'],text=case['text'])))
                        rows.append({**case,'predicted_intent':route.intent,'predicted_clarification':route.needs_clarification})
                    except Exception as exc:
                        rows.append({**case,'predicted_intent':'ERROR','predicted_clarification':False,'error_type':type(exc).__name__})
                if suite=='routing':
                    confusion=Counter((r['intent'],r['predicted_intent']) for r in rows)
                    f1=[]
                    for intent in ['product_question','order_status','escalate_to_human']:
                        tp=sum(r['intent']==intent and r['predicted_intent']==intent and not r['predicted_clarification'] for r in rows)
                        fp=sum(r['intent']!=intent and r['predicted_intent']==intent for r in rows)
                        fn=sum(r['intent']==intent and (r['predicted_intent']!=intent or r['predicted_clarification']) for r in rows)
                        f1.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
                    metrics={'accuracy':sum(r['intent']==r['predicted_intent'] and not r['predicted_clarification'] for r in rows)/len(rows),
                        'macro_f1':sum(f1)/3,'confusion_matrix':{f'{a}->{b}':n for (a,b),n in confusion.items()}}
                else:metrics={'clarification_rate':sum(r['predicted_clarification'] for r in rows)/len(rows)}
            elif suite=='input':
                regex=RegexGuard()
                for case in cases('input_safety.jsonl'):
                    rule=regex.check(case['text'])
                    try:
                        blocked=bool(rule) or not InputDecision.model_validate(await llm.complete_json(read_prompt('input_guard.md'),
                            {'untrusted_customer_message':case['text']})).allowed
                        rows.append({**case,'predicted_blocked':blocked,'regex_rule':rule})
                    except Exception as exc:
                        rows.append({**case,'predicted_blocked':True,'error_type':type(exc).__name__})
                metrics=binary_metrics([r for r in rows if 'error_type' not in r],'blocked','predicted_blocked')
                metrics['provider_errors']=sum('error_type' in r for r in rows)
                metrics['completed_checks']=sum('error_type' not in r for r in rows)
                metrics['note']='Operational errors fail closed and are excluded from semantic recall/false-positive denominators.'
            elif suite=='output':
                docs={d.document_id:d for d in load_documents(settings.kb_dir)}
                for case in cases('output_safety.jsonl'):
                    doc=docs[case['document_id']]
                    try:
                        verdict=SupportDecision.model_validate(await llm.complete_json(read_prompt('output_guard.md'),
                            {'question':'Verify this customer-facing support claim.',
                             'draft':{'status':'answer','claims':[{'text':case['claim'],'citations':[doc.document_id]}]},
                             'reference_documents':[{'document_id':doc.document_id,'content':doc.body}]}))
                        rows.append({**case,'rejected':not verdict.supported,'should_reject':not case['supported']})
                    except Exception as exc:
                        rows.append({**case,'rejected':True,'should_reject':not case['supported'],'error_type':type(exc).__name__})
                metrics=binary_metrics([r for r in rows if 'error_type' not in r],'should_reject','rejected')
                metrics['provider_errors']=sum('error_type' in r for r in rows)
                metrics['completed_checks']=sum('error_type' not in r for r in rows)
            elif suite=='tools':
                repository=FixtureOrders(settings.fixture_path)
                for case in cases('tool_authorization.jsonl'):
                    try:authorize_order(repository.get(case['order_id']),case['customer_id']);allowed=True
                    except Exception:allowed=False
                    rows.append({**case,'actual_allowed':allowed})
                metrics={'accuracy':sum(r['allowed']==r['actual_allowed'] for r in rows)/len(rows),
                    'unauthorized_allowed':sum(not r['allowed'] and r['actual_allowed'] for r in rows)}
            else:
                # Separate workloads and a fresh namespace per workload.
                metrics={}
                for workload in ['unique','repeated']:
                    local_cache=RedisClassifierCache(redis,prefix+':'+workload)
                    local_classifier=Classifier(llm,local_cache)
                    texts=[f'Which filter fits Pure Plus? Reference note {i}.' for i in range(30)] if workload=='unique' else [f'Which filter fits Pure Plus? Reference note {i%5}.' for i in range(30)]
                    for i,text in enumerate(texts):
                        await local_classifier.classify(authority._issue(session,Turn(turn_id=f'cache-{i}',text=text)))
                    metrics[workload]=await local_cache.metrics()
                    rows.append({'workload':workload,'requests':30,'unique_messages':30 if workload=='unique' else 5})
            result['suites'][suite]={'count':len(rows),'metrics':metrics,'rows':rows}
    finally:
        keys=[k async for k in redis.scan_iter(match=prefix+':*')]
        if keys:await redis.delete(*keys)
        await redis.aclose();await llm.aclose()
    result['dataset_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'evaluation/datasets').glob('*.jsonl')}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'Saved live evaluation to {args.output}')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--suite',choices=['all','routing','ambiguity','input','output','tools','cache'],default='all')
    p.add_argument('--live',action='store_true',required=True,help='Explicitly authorize real Groq evaluation calls')
    p.add_argument('--output',type=Path,default=Path('var/evaluation/support-live.json'))
    args=p.parse_args();asyncio.run(run(args))

if __name__=='__main__':main()
