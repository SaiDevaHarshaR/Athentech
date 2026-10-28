"""Offline test of the stage-2 matcher: paraphrases must map to the right known question; look-alikes must be left alone. Run: python tests/test_intent_match.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from agent.intent_match import canonical

POS = {
"How many bills did I get this month?": ["how many invoices were generated this month", "number of bills this month", "how many bills this month", "count of invoices in this month", "how many bills have been made this month"],
"How many bills did I get last month?": ["how many invoices did we get last month", "number of bills last month", "how many bills were there in the previous month", "invoice count for last month"],
"What is my total billed amount in the last 3 months?": ["total billing amount for the last three months", "what is the total billed in last 3 months", "how much did we get billed in the past 3 months", "last 3 months total bill amount"],
"What is my outstanding balance?": ["how much do we owe", "what is the amount due", "what are our dues", "how much money is outstanding", "what is the outstanding amount", "how much balance do we have to pay"],
"What is my credit limit?": ["what is the credit limit", "how much is our credit limit", "tell me our credit limit", "what's my credit ceiling"],
"When was my last payment and how much?": ["when did we last pay and how much", "what was the last payment amount and date", "date and amount of my latest payment", "when was the previous payment made and how much"],
"Has our payment been received?": ["did you receive our payment", "was our payment received", "have you got our payment", "is our payment credited"],
"What services do you provide?": ["which services do you offer", "what facilities do you provide", "what all services are available", "what services does the lab offer"],
"What is the status of my reports?": ["status of our reports", "how are my reports", "what is the progress of my reports", "are my reports ready"],
"How much is pending against our account?": ["how much is pending on our account", "what amount is pending against our account", "how much is pending in our account"],
"What is our available credit limit?": ["how much credit limit is left", "what is the available credit limit", "what credit limit remains available", "how much of our credit limit is available"],
"Can you provide the monthly billing statement?": ["please give the monthly billing statement", "can I get the monthly statement", "i need the monthly billing statement", "send the monthly bill statement"],
"Which tests are still pending?": ["which tests are not completed yet", "tests that are not done yet", "which tests are pending", "what tests are pending", "show pending tests", "list of pending tests", "which investigations are still pending"],
"Which orders are likely to be delayed?": ["which orders may be delayed", "which tests might get delayed", "what orders are likely to be late", "which orders will be delayed"],
"What percentage of reports met TAT this month?": ["what percent of reports met the turnaround time this month", "TAT percentage this month", "how many percent of reports were within TAT this month"],
"Which tests were ordered most frequently?": ["which tests are ordered the most", "most frequently ordered tests", "which tests are ordered most often", "top ordered tests"],
"What is our sample rejection percentage?": ["what percent of samples were rejected", "sample rejection rate", "what is the rejection percentage of samples", "how many percent samples are rejected"],
"Compare our last three months' invoices.": ["compare the invoices of the last three months", "compare invoices for the last 3 months", "compare our last 3 months invoices", "comparison of last three months bills"],
"What health-check packages are available?": ["which health packages are available", "what health checkup packages do you have", "show the health packages", "list the available health check packages"],
"Can you arrange sample pickup tomorrow?": ["can you arrange a sample pickup for tomorrow", "arrange sample pickup tomorrow", "please schedule a sample pickup tomorrow", "i need a sample pickup tomorrow"],
"Can I speak with the lab manager?": ["i want to talk to the lab manager", "can i talk to the manager", "please connect me to the lab manager", "i want to speak to the lab manager"],
"Download Excel": ["download the excel", "i want an excel download", "give me the excel file", "export to excel"],
"Raise a delay complaint": ["raise a complaint about the delay", "i want to complain about a delay", "register a delay complaint", "file a delay complaint"],
"Show rejected samples": ["list the rejected samples", "which samples were rejected", "show me rejected samples", "rejected samples list"],
"Request invoice copy": ["i need a copy of the invoice", "please send the invoice copy", "request a copy of my invoice", "invoice copy request"],
"Request GST invoice copy": ["i need the gst invoice copy", "send the copy of the gst invoice", "gst invoice copy please"],
"Raise renewal request": ["i want to renew the contract", "raise a renewal request", "request renewal", "register a renewal request"],
"Raise recollection request": ["raise a request for sample recollection", "i need recollection of a sample", "recollection request please"],
"Payment status": ["status of my payment", "what is the payment status", "show payment status", "payments status"],
"Status of my reports this month": ["this month report status", "status of the reports this month", "how are my reports this month"],
"Raise a special rate request": ["i want a special rate", "request a special rate", "raise a request for special rates", "can i get a special rate request raised"],
"Top 10 recent bills": ["show the latest 10 bills", "last 10 bills", "show my 10 most recent bills", "recent 10 invoices"],
"Raise a support request": ["i need support", "raise a support ticket", "create a support request", "i want to raise a support ticket"],
"Billing total this month": ["total billing this month", "what is this month's billing total", "billing total for this month", "total billed this month"],
"When is the next payment due?": ["when is my next payment due", "when do we have to pay next", "next payment due date", "what is the due date of the next payment"],
"Which invoices are unpaid?": ["which invoices have not been paid", "show unpaid invoices", "list of unpaid bills", "which bills are unpaid"],
"Tests done this month": ["how many tests were done this month", "tests performed this month", "number of tests this month", "tests carried out this month"],
"Contract agreement details": ["give me the contract details", "show the agreement details", "details of our contract agreement", "what are the contract details"],
"Has our NEFT payment been received?": ["did you receive the neft payment", "was our neft payment received", "have you received our neft"],
"How much credit is available?": ["how much credit do we have left", "what credit is available", "how much credit is left", "available credit amount"],
"When does our agreement expire?": ["when does the contract expire", "when does our contract end", "what is the contract expiry date", "till when is our agreement valid"],
"Has our credit note been approved?": ["was the credit note approved", "is our credit note approved", "credit note approval status"],
"Can we download our ledger?": ["can i download the ledger", "i want to download our ledger", "give me our ledger", "download the ledger"],
"Has our monthly invoice been generated?": ["was the monthly invoice generated", "is the monthly invoice ready", "has this month's invoice been generated", "has the monthly invoice been made"],
"Which branch has the highest test volume?": ["which branch has the most tests", "which branch sends the most tests", "branch with the highest number of tests", "which branch has the highest volume"],
"How has our test volume changed this quarter?": ["how did our test volume change this quarter", "quarterly test volume change", "has our test volume changed this quarter", "test volume trend this quarter"],
"Give me today's pending-order summary.": ["summary of today's pending orders", "give me a summary of pending orders today", "today's pending orders summary", "what are today's pending orders"],
}
NEG = [  # must NOT be rewritten (different question, names, codes)
 "what is the price of lipid profile", "price of thyroid panel", "what is the status of bill SMN26190603", "which tests are in bill SMN123", "show bills of patient Ravi",
 "what is the rate of vitamin D test", "is fasting required for the sugar test", "what is included in the full body checkup package", "where is the sample for bill SMN123",
 "how many bills did patient Ravi have", "what is the report time for lipid profile", "how do i reset my password", "what is the weather today", "who is the owner of the lab",
 "what are the lab timings", "where is the lab located", "how much is the thyroid test", "give me the phone number of the lab", "email the report to me", "what is the address of central lab",
 "what is the price of CBC", "can you recommend a good doctor", "how many patients came yesterday", "what is the status of sample 4455", "which doctor referred the most patients",
 "show the report of patient Suresh", "what is the cost of vitamin B12 test and when will it be ready", "what is the credit period", "what is the tax on my invoice",
 "do you offer home collection", "how do i pay online", "what is your refund policy",
]
bad = 0
miss = 0
total = 0
for want, qs in POS.items():
    for q in qs:
        total += 1
        got, sc = canonical(q)
        if got is None:
            miss += 1
            print("unmapped %-55s (%.2f) want %s" % (q, sc, want))
        elif got != want:
            bad += 1
            print("WRONG %-60s -> %s (%.2f) want %s" % (q, got, sc, want))
print("positives: %d/%d correct, %d unmapped (left to the AI, not wrong), %d WRONG" % (total - bad - miss, total, miss, bad))
leak = 0
for q in NEG:
    got, sc = canonical(q)
    if got:
        leak += 1
        print("LEAK  %-60s -> %s (%.2f)" % (q, got, sc))
print("negatives: %d/%d left alone" % (len(NEG) - leak, len(NEG)))
sys.exit(1 if (leak or bad) else 0)
