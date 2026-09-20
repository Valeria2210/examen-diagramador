import os
os.environ['GENERATED_API_URL'] = 'http://127.0.0.1:58089'
import generador.smoke_generated as smoke
from generador.smoke_generated import request

smoke.authenticate()

client = request('POST', '/api/clientes', {'nombre': 'Audit sin relaciones'}, 201)
order = request('POST', '/api/pedidos', {'total': 1}, 201)
print('PEDIDO_SIN_CLIENTE', order['clienteId'])
request('PUT', '/api/clientes/' + str(client['codigoCliente']), {'nombre': 'Audit inversa', 'pedidosIds': [order['codigoPedido']]})
print('RELACION_INVERSA_IGNORADA', request('GET', '/api/pedidos/' + str(order['codigoPedido']))['clienteId'])
request('DELETE', '/api/pedidos/' + str(order['codigoPedido']), expected=204)
request('DELETE', '/api/clientes/' + str(client['codigoCliente']), expected=204)
smoke.TOKEN = None
request('GET', '/api/clientes', expected=401)
print('API_SIN_TOKEN_401_OK')
