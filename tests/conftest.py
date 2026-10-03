"""All tests are offline. Accidental network use is a hard failure."""
import socket
import pytest

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Network access is forbidden in offline validation')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    from curl_cffi.requests import Session,AsyncSession
    monkeypatch.setattr(Session,'request',forbidden)
    monkeypatch.setattr(AsyncSession,'request',forbidden)
