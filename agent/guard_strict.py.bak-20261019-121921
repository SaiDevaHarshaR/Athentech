"""Strict, code-level guardrails (not prompt-level). Installed at runtime by guard_hooks.

screen_input(q)  -> (ok, reply)   blocks injection, prompt/secret/tenant exfiltration, write/DDL intent, off-topic
screen_output(t) -> text          strips SQL, table dumps, secrets, connection strings, leaked prompt text
"""
import re
import unicodedata

_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

REFUSE = "I can only help with questions about your hospital/lab data in Sahasra."
R_INJECT = "I can't process that request. Ask me about your hospital/lab data."
R_SECRET = "I can't share system details, credentials or other organisations' data."
R_WRITE = "I can only read and report data. I can't add, change or delete records. Please do that in Sahasra."


def _norm(t):
    t = unicodedata.normalize("NFKC", t or "").translate(_ZW).lower()
    return re.sub(r"\s+", " ", t).strip()


def _leet(t):
    return re.sub(r"[^a-z0-9 ]+", " ", t.translate(_LEET))


INJECT = [
    r"(ignore|disregard|forget|override|skip)\b.{0,25}\b(previous|prior|above|earlier|all|your|system)\b.{0,25}\b(instruction|rule|prompt|guideline|restriction|polic)",
    r"\b(jailbreak|dan mode|developer mode|god mode|sudo mode|unrestricted mode|do anything now)\b",
    r"\b(bypass|disable|turn off|remove)\b.{0,20}\b(filter|guardrail|safety|restriction|security|rule)",
    r"\b(pretend|act|behave|roleplay|role play|imagine)\b.{0,25}\b(you are|you're|as if|to be|like)\b.{0,40}\b(no (rule|restriction|limit)|unrestricted|different ai|another ai|evil|hacker|dan)\b",
    r"\bact as\b.{0,30}\b(unrestricted|jailbroken|hacker|dan|root|admin)\b",
    r"\bfrom now on\b.{0,40}\b(you (will|are|must)|ignore|answer anything)",
    r"\bnew (instruction|rule|system prompt)s?\s*[:=]",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
    r"\[\s*(system|inst)\s*\]",
    r"\bsystem\s*:\s*you are\b",
]

SECRET = [
    r"(system|initial|hidden|original|secret|internal)\s*(prompt|instruction|message|rule)s?",
    r"(show|reveal|print|repeat|display|tell|give|leak|dump|share).{0,30}(your|the)\s*(prompt|instructions|rules|configuration|config|system message)",
    r"what (are|were) your (instruction|rule|prompt)s?",
    r"\b(api[\s_-]?key|secret key|access token|bearer token|password|passwd|credential|connection string|conn string|db password|database password|private key|\.env)\b",
    r"\b(groq|openai|anthropic|gemini|nssm|pyodbc|sqlalchemy|langchain|fastapi)\b.{0,20}\b(key|token|secret|config)",
    r"\b(other|another|different|competitor)\b.{0,15}\b(hospital|clinic|lab|tenant|organi[sz]ation|institution|database|activation code)s?\b",
    r"\b(list|show|dump|give|tell|how many).{0,20}\b(all )?(databases|tenants|activation codes|institutions)\b",
    r"\b(sys\.|information_schema|sysobjects|syscolumns|master\.\.|msdb|xp_cmdshell|sp_configure|sp_executesql|openrowset|bulk insert)\b",
    r"\b(show|list|dump)\b.{0,12}\b(all )?(table|column|schema)s?\s*(names?|list)?\b.{0,10}$",
    r"\b(server|host|ip) (address|name)\b|\bwhich (server|database) (are|is) you\b",
]

WRITE = [
    r"\b(delete|remove|drop|truncate|erase|wipe|purge)\b.{0,25}\b(patient|bill|record|row|table|data|entry|entries|invoice|test|report|database|user)s?\b",
    r"\b(update|change|edit|modify|alter|set|correct)\b.{0,25}\b(patient|bill|record|amount|price|rate|result|name|phone|mobile|status|date|value|report)s?\b.{0,25}\b(to|as|=|with)\b",
    r"^(please |pls |can you |could you )?(insert|add|create|register)\b.{0,20}\b(new )?(patient|bill|record|row|entry|invoice|user|test)s?\b",
    r"\b(drop|truncate|alter|create)\s+(table|database|schema|index|view|procedure)\b",
    r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from)\b",
    r"^(please |pls |can you |could you )?(approve|cancel|refund|reverse|void)\b.{0,15}\b(bill|payment|invoice)\b",
    r"\b(grant|revoke)\s+(all|select|insert|update|delete)\b",
    r";\s*(drop|delete|update|insert|exec|truncate|alter)\b",
    r"\b(exec|execute)\s+(sp_|xp_)",
]

# Words that make a question "about the data". If any is present we do NOT call it off-topic.
DOMAIN = re.compile(
    r"\b(patient|uhid|bill|billing|invoice|revenue|collection|collected|income|sales|payment|cash|upi|card|due|dues|outstanding|"
    r"refund|discount|concession|doctor|dr|referral|referred|physician|consultant|test|tests|lab|laborator|sample|specimen|"
    r"report|result|pending|approved|critical|abnormal|tat|turnaround|department|dept|radiology|pathology|biochem|"
    r"microbiolog|hematolog|haematolog|serolog|branch|location|centre|center|collection point|franchise|b2b|client|corporate|"
    r"admission|admitted|discharge|ipd|opd|bed|ward|surgery|prescription|appointment|visit|encounter|pharmacy|"
    r"insurance|tpa|claim|package|profile|panel|parameter|barcode|accession|home collection|phlebotom|"
    r"summary|dashboard|"
    r"sahasra|hospital|clinic|staff|employee|inventory|stock|expense|ledger|gst|tax|outsourc|rate list|tariff)\w*",
    re.I)

OFFTOPIC = [
    r"\b(weather|temperature outside|forecast|stock price|share price|bitcoin|crypto|cricket score|ipl|football|movie|song|lyrics|"
    r"recipe|horoscope|astrology|news|election|prime minister|president|capital of|who (is|was) the|when (was|did)|"
    r"translate|poem|poetry|story|essay|joke|riddle|song|rap|haiku|homework|math problem|solve|equation|"
    r"write (me )?(a |an )?(code|program|script|function|email|letter|essay|poem|story)|python|javascript|java code|html|"
    r"explain (quantum|relativity|blockchain)|meaning of life|tell me about yourself|who (made|created|built) you|"
    r"which (llm|model)|are you (chatgpt|gpt|claude|gemini|llama)|your name)\b",
    r"\b(what (medicine|tablet|drug|pill)|diagnos|prescribe|treatment for|cure for|symptoms of|side effects? of|dosage|home remedy|should i take|am i (sick|pregnant)|medical advice)\w*",
    r"\b(legal advice|lawyer|sue|tax advice|investment advice|loan|dating|relationship advice)\b",
]

WEAK = re.compile(r"\b(today|yesterday|week|month|year|daily|monthly|total|count|how many|average|top|trend|compare|vs)\b", re.I)

GREET = re.compile(r"^(hi+|hello+|hey+|hola|namaste|good (morning|afternoon|evening)|thanks?( you)?|thank u|ok(ay)?|bye|help|menu|\?|yes|no|yep|nope|sure|cool|great)\W*$", re.I)


def _hit(pats, *texts):
    for p in pats:
        for t in texts:
            if re.search(p, t, re.I):
                return p
    return None


def screen_input(q):
    """-> (ok, reply). Never raises."""
    try:
        raw = q if isinstance(q, str) else str(q or "")
        if len(raw) > 2000:
            return False, "That message is too long. Please ask a shorter question."
        t = _norm(raw)
        if not t or GREET.match(t):
            return True, ""
        lt = _leet(t)
        if _hit(INJECT, t, lt):
            return False, R_INJECT
        if _hit(SECRET, t, lt):
            return False, R_SECRET
        if _hit(WRITE, t):
            return False, R_WRITE
        if _hit(OFFTOPIC, t) and not DOMAIN.search(t):
            return False, REFUSE
        # long text with no data words at all and not a question about data
        if len(t.split()) >= 4 and not DOMAIN.search(t) and not WEAK.search(t) and not re.search(r"\b(show|list|give|what|how|which|who|when|where|count|find|get|display|compare|tell)\b", t):
            return False, REFUSE
        return True, ""
    except Exception:
        return True, ""


_OUT_PATTERNS = [
    (re.compile(r"\b(gsk_|sk-|AIza|ghp_|xox[bp]-)[A-Za-z0-9_\-]{12,}"), "[hidden]"),
    (re.compile(r"(?i)\b(password|pwd|passwd|secret|api[_ -]?key|token)\s*[:=]\s*\S+"), "[hidden]"),
    (re.compile(r"(?i)\b(server|data source|uid|user id|pwd|driver)\s*=\s*[^;\n]+;?"), "[hidden]"),
    (re.compile(r"(?is)```\s*sql.*?```"), ""),
    (re.compile(r"(?is)\b(select\s+.{1,300}?\s+from\s+\w+.*?)(?=\n\n|$)"), ""),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED]"),
    (re.compile(r"(?i)\byou are (the )?sahasra[^.\n]*assistant[^\n]*"), ""),
    (re.compile(r"(?i)(TOPIC BOUNDARY|PRE-VERIFIED SCHEMA|INTEGRITY_RULES|STYLE_RULES)[^\n]*"), ""),
]


def screen_output(text):
    try:
        if not isinstance(text, str):
            return text
        if "```dashboard-card" in text or "```list-card" in text:
            parts = re.split(r"(```(?:dashboard-card|list-card).*?```)", text, flags=re.S)
            return "".join(p if p.startswith("```dashboard") or p.startswith("```list") else _clean(p, False) for p in parts)
        return _clean(text)
    except Exception:
        return text


def _clean(t, whole=True):
    for rx, rep in _OUT_PATTERNS:
        t = rx.sub(rep, t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return (t.strip() or "I could not find that in your data.") if whole else t
