import asyncio
import pytest
import config
from network_engine import NetworkEngine
from forge2_experiments import IndeterminateAttemptError


@pytest.mark.parametrize('failure',['transport','server'])
def test_ambiguous_simulation_post_is_not_automatically_retried(monkeypatch,failure):
    monkeypatch.setattr(config,'SAFE_SIMULATION_WRITES',True,raising=False)
    monkeypatch.setattr(config,'RESEARCH_OFFLINE_ONLY',False,raising=False)
    class Rate:
        async def wait(self):pass
    class Session:
        calls=0
        async def request(self,*a,**k):
            self.calls+=1
            if failure=='transport':raise OSError('unknown remote acceptance')
            return type('Response',(),{'status_code':500})()
    obj=NetworkEngine.__new__(NetworkEngine);obj._rate_limiter=Rate();obj.session=Session();obj.cookie='fixture'
    async def exercise():
        with pytest.raises(IndeterminateAttemptError):await obj.request('POST','/simulations',json={})
        assert obj.session.calls==1
    asyncio.run(exercise())


def test_internal_429_loop_has_a_bound_without_external_timeout(monkeypatch):
    monkeypatch.setattr(config,'RESEARCH_OFFLINE_ONLY',False,raising=False)
    monkeypatch.setattr(config,'NETWORK_MAX_TOTAL_ATTEMPTS',3,raising=False)
    class Rate:
        async def wait(self):pass
        async def defer(self,*a):pass
    class Session:
        calls=0
        async def request(self,*a,**k):
            self.calls+=1
            return type('Response',(),{'status_code':429,'headers':{'Retry-After':'0'}})()
    obj=NetworkEngine.__new__(NetworkEngine);obj._rate_limiter=Rate();obj.session=Session();obj.cookie='fixture'
    async def exercise():
        with pytest.raises(TimeoutError):await obj.request('GET','/job/fixture')
        assert obj.session.calls==3
    asyncio.run(exercise())
