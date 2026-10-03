import random
from forge2_queue import prioritize

def test_prioritization_reorders_but_never_drops_or_duplicates():
    rows=[('f'+str(i),'U',0) for i in range(20)]
    order=prioritize(rows,lambda expr,u,d:int(expr[1:]),rng=random.Random(2))
    assert sorted(order)==sorted(rows)
    assert order[0]!=rows[0]

def test_missing_model_and_failed_scores_preserve_candidates():
    rows=[('a','U',0),('b','U',1)]
    assert prioritize(rows,lambda *a:None)==rows
    assert prioritize(rows,lambda *a:float('nan'))==rows
