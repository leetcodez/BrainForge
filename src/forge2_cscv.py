"""Bounded CSCV selection diagnostic for a FIXED synchronized return pool.
Not chronological walk-forward deployability, not full adaptive-search PBO.
"""
import itertools,math
import numpy as np
from scipy.stats import rankdata


def cscv_fixed_pool(values,blocks=8,max_partitions=1000):
    x=np.asarray(values,dtype=float)
    if x.ndim!=2 or x.shape[1]<2 or not np.isfinite(x).all():raise ValueError('Need a complete synchronized 2D return pool')
    if type(blocks) is not int or blocks<4 or blocks%2 or x.shape[0]%blocks or x.shape[0]//blocks<5:raise ValueError('Need even equal time blocks with at least five rows; no silent trimming')
    count=math.comb(blocks,blocks//2)
    if count>max_partitions:raise ValueError('CSCV partition budget exceeded')
    indices=np.arange(len(x)).reshape(blocks,-1);logits=[];selections=[];ties=0
    for chosen in itertools.combinations(range(blocks),blocks//2):
        other=[b for b in range(blocks) if b not in chosen]
        train=x[indices[list(chosen)].ravel()];test=x[indices[other].ravel()]
        train_sd=train.std(axis=0);test_sd=test.std(axis=0)
        if np.any(train_sd<=1e-12) or np.any(test_sd<=1e-12):raise ValueError('Flat candidate in a partition; undefined ranks')
        is_scores=train.mean(axis=0)/train_sd;oos_scores=test.mean(axis=0)/test_sd
        winners=np.flatnonzero(is_scores==is_scores.max());winner=int(winners[0]);ties+=len(winners)>1
        # Higher score receives higher ascending rank. M+1 avoids endpoints;
        # median ties produce lambda=0 and are not counted as negative logits.
        omega=float(rankdata(oos_scores,method='average')[winner]/(x.shape[1]+1))
        logits.append(math.log(omega/(1-omega)));selections.append(winner)
    return {'metric':'cscv_fixed_pool_pbo','fraction_negative_logits':sum(v<0 for v in logits)/len(logits),
            'partitions':len(logits),'blocks':blocks,'pool_columns':x.shape[1],'observations':len(x),
            'winner_columns':selections,'logits':logits,'is_tie_partitions':int(ties),
            'tie_policy':'first column for IS ties, average OOS ranks; zero logit not negative',
            'caveat':'Fixed preselected complete pool only; symmetric non-forward splits do not certify chronological deployability or count unrecorded adaptive trials'}
