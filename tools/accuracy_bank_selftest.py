import sys, os, sqlite3, types, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.environ.setdefault('GROQ_API_KEY', 'x')
sys.modules.setdefault('pyodbc', types.ModuleType('pyodbc'))
from datetime import date
from agent import accuracy_bank as ab
import agent.schema_ctx as sc
sc.coll_amt = lambda p, alias="": "AMT"; sc.pri_amt = lambda p, alias="": "p.TOT"
c = sqlite3.connect(':memory:')
c.executescript("""create table trninvlabpri(BILLNO,BILLDATE,REFDOCTCODE,TOT);create table mstpatientregistration(REGDATE);
create table trnmodeofcollectionsdet(DATEOFBILL,AMT,MODE,TYPE,CONCESSIONAMOUNT);create table trninvstatus(STATUS,AUTHENTICATEDATE);
create table trninvlabdet(BILLDATE,TESTSTATUS,TCODE);create table mstInvestigations(INVCODE,INVNAME);create table mstrefdoctor(DOCID,DOCNAME);""")
t = date.today().isoformat()
for i in range(7): c.execute("insert into trninvlabpri values(?,?,?,?)", (i, t, 1 + i % 2, 100))
c.execute("insert into mstrefdoctor values(1,'Dr. Rao')"); c.execute("insert into mstrefdoctor values(2,'Dr. Sen')")
for i in range(3): c.execute("insert into mstpatientregistration values(?)", (t,))
c.execute("insert into trnmodeofcollectionsdet values(?,?,?,?,?)", (t, 78200.0, 'Cash', 'X', 50)); c.execute("insert into trnmodeofcollectionsdet values(?,?,?,?,?)", (t, 1000.0, 'UPI', 'X', 0))
c.execute("insert into mstInvestigations values(1,'CBP')")
for i in range(4): c.execute("insert into trninvlabdet values(?,?,1)", (t, 'Done'))
c.execute("insert into trninvlabdet values(?,?,1)", (t, 'Cancelled'))
ans = lambda q: "Bills: 7. Patients 3. Collection ₹79,200. Cash ₹78,200. Concession 50. Tests 5. Cancelled 1. Top test CBP. Dr. Rao top. " if "authent" not in q else "none"
r = ab.run_client("T", ask=ans, connect=lambda: c, profile_fn=lambda cn: {"pat_date": "REGDATE"}, periods=["today"], per_kind=1, rng=random.Random(1))
for x in r["results"]: print(x["kind"], x["period"], x["status"], x["question"], "|", x.get("note", "")[:60])
print(r["accuracy"], r["passed"], r["failed"], r["skipped"])
