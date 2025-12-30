import sys
import os
import pytest
from importlib import import_module

# Ajuste o caminho para importar o módulo corretamente
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../addon/FreeCADMCP/rpc_server')))

# Teste mínimo para garantir importação e inicialização

def test_import_rpc_server():
    try:
        rpc_server = import_module('rpc_server')
    except Exception as e:
        pytest.fail(f'Falha ao importar rpc_server: {e}')

def test_start_stop_rpc_server():
    rpc_server = import_module('rpc_server')
    # Testa inicialização e parada do servidor (mock, sem rodar de fato)
    assert hasattr(rpc_server, 'start_rpc_server')
    assert hasattr(rpc_server, 'stop_rpc_server')
