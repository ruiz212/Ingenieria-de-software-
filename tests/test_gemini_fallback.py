from types import SimpleNamespace
import pytest
import requests


def response(status=200, text='hola', **kwargs):
    data = kwargs.pop('data', {'candidates': [{'content': {'parts': [{'text': text}]}}]})
    return SimpleNamespace(status_code=status, headers=kwargs, json=lambda: data)


def client(monkeypatch, replies, clock=None, models=('gemini-3.8-flash', 'gemini-3.6-flash')):
    from app.whatsapp.gemini import Gemini
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    monkeypatch.delenv('WHATSAPP_MODEL', raising=False)
    monkeypatch.delenv('WHATSAPP_MODELS', raising=False)
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        value = replies.pop(0)
        if isinstance(value, Exception): raise value
        return value
    return Gemini(models=models, post=post, clock=clock or (lambda: 100)), calls


def test_429_switches_models_and_remembers_cooldown(monkeypatch):
    bot, calls = client(monkeypatch, [response(429, **{'Retry-After': '120'}), response(), response()])
    assert bot.complete([{'role':'user','text':'hola'}], [])['text']=='hola'
    bot.complete([{'role':'user','text':'otra consulta'}], [])
    assert len(calls)==3
    assert '3.8-flash' in calls[0][0] and all('3.6-flash' in c[0] for c in calls[1:])


def test_primary_recovers_after_server_retry_delay(monkeypatch):
    now=[100]
    bot,calls=client(monkeypatch,[response(429,data={'error':{'details':[{'retryDelay':'5s'}]}}),response(),response()],clock=lambda:now[0])
    bot.complete([{'role':'user','text':'a'}],[])
    now[0]=161
    bot.complete([{'role':'user','text':'b'}],[])
    assert '3.8-flash' in calls[-1][0]


@pytest.mark.parametrize('status',[400,401,403])
def test_does_not_rotate_on_invalid_request_or_credentials(monkeypatch,status):
    bot,calls=client(monkeypatch,[response(status),response()])
    with pytest.raises(RuntimeError): bot.complete([{'role':'user','text':'hola'}],[])
    assert len(calls)==1


@pytest.mark.parametrize('failure',[response(503),response(404),requests.Timeout('synthetic')])
def test_rotates_on_service_failure_or_retired_model(monkeypatch,failure):
    bot,calls=client(monkeypatch,[failure,response()])
    assert bot.complete([{'role':'user','text':'hola'}],[])['text']=='hola'
    assert len(calls)==2


def test_exhaustion_is_bounded_and_next_request_does_not_hammer_api(monkeypatch):
    bot,calls=client(monkeypatch,[response(429),response(429)])
    for _ in range(2):
        with pytest.raises(RuntimeError): bot.complete([{'role':'user','text':'hola'}],[])
    assert len(calls)==2


def test_empty_safety_block_does_not_rotate_to_bypass_it(monkeypatch):
    bot,calls=client(monkeypatch,[response(data={'promptFeedback':{'blockReason':'SAFETY'}}),response()])
    with pytest.raises(RuntimeError): bot.complete([{'role':'user','text':'hola'}],[])
    assert len(calls)==1


def test_keeps_signed_model_parts_for_same_model(monkeypatch):
    parts=[{'functionCall':{'name':'consultar_catalogo','args':{}},'thoughtSignature':'synthetic-signature'}]
    bot,calls=client(monkeypatch,[response(data={'candidates':[{'content':{'parts':parts}}]}),response()])
    answer=bot.complete([{'role':'user','text':'catálogo'}],[])
    bot.complete([{'role':'user','text':'catálogo'}, {'role':'model','parts':answer['parts'],'source_model':answer['model']},
                  {'role':'user','result':{'name':'consultar_catalogo','response':[]}}],[])
    assert calls[-1][1]['json']['contents'][1]['parts']==parts


def test_cross_model_failover_keeps_tool_result_but_not_foreign_signature(monkeypatch):
    bot,calls=client(monkeypatch,[response(429),response()])
    bot.complete([{'role':'user','text':'catálogo'},
      {'role':'model','source_model':'gemini-3.8-flash','parts':[{'functionCall':{'name':'consultar_catalogo','args':{}},'thoughtSignature':'foreign'}]},
      {'role':'user','result':{'name':'consultar_catalogo','response':[{'nombre':'Pan','precio':15}]}}],[])
    payload=str(calls[-1][1]['json']['contents'])
    assert 'Pan' in payload and 'foreign' not in payload and 'functionResponse' not in payload


def test_model_list_deduplicates_and_rejects_unsafe_names(monkeypatch):
    bot,_=client(monkeypatch,[],models=('gemini-3.8-flash','gemini-3.8-flash'))
    assert len(bot.models)==1
    with pytest.raises(ValueError): client(monkeypatch,[],models=('gemini/x?key=secret',))


def test_primary_uses_supported_low_thinking_for_chat_latency(monkeypatch):
    bot,calls=client(monkeypatch,[response()])
    bot.complete([{'role':'user','text':'hola'}],[])
    assert calls[0][1]['json']['generationConfig']['thinkingConfig']=={'thinkingLevel':'LOW'}


def test_agent_answers_all_parallel_calls_once_and_preserves_signatures():
    from app.whatsapp.agent import Agent
    signed=[{'functionCall':{'name':'consultar_catalogo','args':{},'id':'c1'},'thoughtSignature':'signed'},
            {'functionCall':{'name':'consultar_mis_cotizaciones','args':{},'id':'c2'}}]
    class Model:
        n=0
        def complete(self,messages,schemas):
            self.n+=1
            if self.n==1: return {'parts':signed,'model':'gemini-3.8-flash','calls':[p['functionCall'] for p in signed]}
            assert messages[-2]['parts']==signed
            assert len(messages[-1]['results'])==2
            assert [r['id'] for r in messages[-1]['results']]==['c1','c2']
            return {'text':'Completado'}
    class Tools:
        schemas=[]
        calls=[]
        def call(self,name,args,key):
            self.calls.append((name,key))
            return []
    tools=Tools()
    assert Agent(Model()).reply('consulta',[],tools,'message')=='Completado'
    assert len(tools.calls)==2 and len({c[1] for c in tools.calls})==2
