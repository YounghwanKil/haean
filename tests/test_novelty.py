from copy import deepcopy
from haean.novelty import audit, digest, remember, history


def row(identity='A',number=10):
    item={'id':identity,'passage':f'가상의 시설에서 각 담당자는 {number}개의 물품을 서로 다르게 배정한다. 담당자는 자신이 점검한 물품을 다시 검수할 수 없으며 모든 검수는 배정 다음 날 이루어진다.', 'cognitive_task':'배정과 검수 금지 조건을 결합해 가능한 순서를 추론', 'essential_conditions':['동일 담당자의 배정과 검수를 금지한다'], 'explanation':'담당자가 점검한 물품의 검수를 제외하면 다른 담당자의 순서만 남는다. 남은 두 조건을 함께 적용해야 유일한 배정이 정해진다.', 'options':[{'text':f'{x}번 배정'} for x in range(5)],'tables':[],'figures':[],'shared_passage_id':None}
    return {'exam':'leet','subject':'추리논증','item':item,'source':'synthetic','sha256':digest(item)}


def test_numeric_reskin_and_revision_identity():
    old=row(); new=row('B',200)
    result=audit([new],[old]);assert result['items'][0]['neighbors'][0]['review_candidate']
    assert not audit([row('A',200)],[old])['items'][0]['neighbors']


def test_shared_passage_not_enough_for_flag():
    a=row();b=row('B');a['item']['shared_passage_id']=b['item']['shared_passage_id']='set-1'
    b['item']['cognitive_task']='';b['item']['essential_conditions']=[];b['item']['explanation']='별개 질문';b['item']['options']=[{'text':'짧은 보기'}]*5
    result=audit([b],[a])['items'][0]['neighbors'][0]
    assert result['shared_passage_pair'] and not result['review_candidate']


def test_catalog_keeps_versions_without_inflating_lineages(tmp_path):
    path=tmp_path/'generated.sqlite'
    assert history(path)==[] and not path.exists()
    assert remember(path,[row()])['current_items']==1
    status=remember(path,[row(number=200)]);assert status['current_items']==1 and status['versions']==2
    assert {x['sha256'] for x in history(path)}=={row()['sha256'],row(number=200)['sha256']}
    result=audit([row('B')],history(path))
    assert result['history_items']==1 and result['history_versions']==2
    assert len(result['items'][0]['neighbors'])==1


def test_same_type_short_labels_do_not_establish_repeat():
    a=row();b=row('B');b['item']['passage']='전혀 다른 지문';b['item']['cognitive_task']='다른 추론';b['item']['essential_conditions']=[];b['item']['explanation']='다른 해설'
    assert not audit([b],[a])['items'][0]['neighbors'][0]['review_candidate']


def test_display_limit_does_not_hide_flagged_questions():
    previous = [row(f'old-{n}', n + 1) for n in range(8)]
    # A second version of one lineage must not become a ninth question.
    previous.append(row('old-0', 999))
    result = audit([row('new', 200)], previous, limit=2)['items'][0]
    assert result['flagged_neighbor_count'] == 8
    assert {hit['previous_id'] for hit in result['neighbors']} == {
        f'old-{n}' for n in range(8)
    }
    assert len(result['neighbors']) == 8


def test_flagged_old_version_survives_higher_ranked_unflagged_revision(monkeypatch):
    from haean import novelty
    candidate = row('new')
    flagged = row('old', 1)
    unflagged = row('old', 2)
    base = set(range(50))

    def overlap(count):
        return set(range(count)) | set(range(100, 150-count))

    vectors = {
        candidate['sha256']: dict(passage=base, reasoning=base, options=base, data=set()),
        flagged['sha256']: dict(passage=overlap(28), reasoning=set(), options=set(), data=set()),
        unflagged['sha256']: dict(passage=overlap(27), reasoning=overlap(14), options=base, data=set()),
    }
    monkeypatch.setattr(novelty, 'features', lambda item: vectors[digest(item)])
    result = audit([candidate], [flagged, unflagged], limit=1)['items'][0]
    assert result['flagged_neighbor_count'] == 1
    assert len(result['neighbors']) == 1
    assert result['neighbors'][0]['previous_sha256'] == flagged['sha256']


def test_old_question_remains_searchable_after_100_other_items(tmp_path):
    import random
    rng = random.Random(42)
    old = row('original')
    others = []
    for n in range(110):
        value = row(f'other-{n:03}')
        # Synthetic dissimilar text, not an LLM-generated long-run benchmark.
        for field in ('passage', 'explanation', 'cognitive_task'):
            value['item'][field] = ''.join(chr(rng.randrange(0xac00,0xd7a3)) for _ in range(120))
        value['item']['essential_conditions'] = []
        value['sha256'] = digest(value['item'])
        others.append(value)
    path = tmp_path/'history.sqlite'
    remember(path,[old]);remember(path,others)
    result = audit([row('new',900)],history(path))
    assert result['history_items'] == 111
    assert result['items'][0]['neighbors'][0]['previous_id'] == 'original'
    assert result['items'][0]['neighbors'][0]['review_candidate']
