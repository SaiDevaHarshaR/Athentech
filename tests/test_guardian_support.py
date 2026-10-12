import json
from agent import guardian_support as s

def test_guide_exists_for_all_categories():
    for category in ['database_connection','schema_changed','query_timeout','licensing','llm_provider','report_export','unknown']:
        assert s.guide(category)

def test_snapshot_detects_change_and_does_not_overwrite(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'SNAP_DIR',tmp_path)
    original=[dict(schema='dbo',table='trnINVLABPRI',column='BILLNO',type='varchar')]
    first=s.compare_snapshot('H022-Test',original,save=True)
    assert not first['baseline_exists'] and first['snapshot_saved']
    changed=original+[dict(schema='dbo',table='trnINVLABPRI',column='TOTALCHARGES',type='decimal')]
    diff=s.compare_snapshot('H022-Test',changed)
    assert len(diff['added'])==1 and not diff['snapshot_saved']
    assert len(json.loads((tmp_path/'H022-Test.json').read_text()))==1

def test_reject_path_traversal():
    try: s.safe_client('../other')
    except ValueError: pass
    else: assert False

def test_bundle_excludes_raw_error_and_patient_values():
    payload={'clients':[{'client':'H022-Test','errors_recent':1,'by_category':{'unknown':1},'circuit_open':False,'last_error':{'category':'unknown','error':'patient name private','message':'Unexpected error','safe_action':'Escalate'}}]}
    text=json.dumps(s.diagnostic_report(payload))
    assert 'patient name private' not in text
