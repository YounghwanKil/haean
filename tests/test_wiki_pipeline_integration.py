import json
from haean import wiki_bridge as W
from haean.pipeline import run_pipeline, save
from haean.staged_authoring import attach, run_staged
from test_wiki_bridge import make_page
from test_compact_authoring_pipeline import Spy
from test_staged_authoring import Provider, prepared, track_brief


def test_legacy_writer_receives_wiki_but_independent_roles_do_not(tmp_path,brief,draft):
    root,_=make_page(tmp_path)
    run=tmp_path/'legacy';run.mkdir()
    save(run/'brief.json',brief.model_dump());save(run/'context.json',{'brief':brief.model_dump(),'references':[{'id':'source-1','text':'synthetic'}]})
    W.snapshot(root,['lesson'],run/'wiki-context.json',track='leet_reasoning',grade=None,reason='합성 적용')
    class Capture(Spy):
        def call(self,stage,instructions,payload,schema):
            seen[stage]=instructions+'\n'+json.dumps(payload)
            return super().call(stage,instructions,payload,schema)
    seen={};run_pipeline(run,Capture(draft),max_revisions=0)
    assert 'WIKI_SENTINEL_ANNOTATION' in seen['generate']
    assert all('WIKI_SENTINEL_ANNOTATION' not in seen[x] for x in ('blind','editor'))


def test_staged_sources_are_in_author_instructions_not_blind_or_editor(tmp_path,draft):
    root,_=make_page(tmp_path);brief=track_brief();run=prepared(tmp_path,brief);attach(run,brief)
    W.snapshot(root,['lesson'],run/'wiki-context.json',track=brief.track,grade=brief.grade,reason='합성 적용')
    provider=Provider(draft);run_staged(run,provider,0)
    seen={stage:instructions+'\n'+json.dumps(payload) for stage,instructions,payload in provider.calls}
    assert all('WIKI_SENTINEL_ANNOTATION' in seen[s] for s in ('material','design','generate'))
    assert all('WIKI_SENTINEL_ANNOTATION' not in seen[s] for s in ('blind','editor'))
