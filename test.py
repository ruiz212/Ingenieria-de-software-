import urllib.request
import json
req = urllib.request.Request('http://127.0.0.1:5000/api/enviar_codigo_sms', method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'telefono':'88881234'}).encode('utf-8'))
try:
    urllib.request.urlopen(req)
except Exception as e:
    print(e.read().decode('utf-8'))
