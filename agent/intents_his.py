"""
HIS (Hospital) intent dispatcher — separate from agent/intents.py (LIS/
diagnostic). No shared tables/intents between the two by design (per
institution.institution_type). Empty for now — real HIS tables need
schema discovery first, same process LIS went through.
"""
def try_intent_his(question, role, db_name, db_server=None, db_user=None, db_password=None):
    return None  