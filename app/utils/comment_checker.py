import re

QUESTION_PATTERNS = [
    r"\?",
    r"\bcan you\b", r"\bcould you\b", r"\bwould you\b", r"\bwill you\b",
    r"\bplease\b", r"\bkindly\b", r"\brequest(ing)?\b",
    r"\bwhen\b", r"\bwhat\b", r"\bwhere\b", r"\bwho\b", r"\bwhy\b", r"\bhow\b",
    r"\bconfirm\b", r"\bverify\b", r"\bcheck\b", r"\breview\b", r"\bapprove\b",
    r"\bshare\b", r"\bprovide\b", r"\bsend\b", r"\battach\b", r"\bupload\b",
    r"\bhelp\b", r"\bassist\b", r"\bsupport\b", r"\bguide\b",
    r"\binvestigate\b", r"\banalyze\b", r"\blook into\b", r"\bexamine\b",
    r"\bfollow up\b", r"\bfollow-up\b", r"\bupdate\b", r"\bstatus\b",
    r"\bresolve\b", r"\bfix\b", r"\baddress\b", r"\bhandle\b",
    r"\bneed your\b", r"\brequire your\b", r"\bexpecting\b",
    r"\bwaiting for\b", r"\bpending your\b", r"\bawaiting\b",
    r"\bblock(ed|ing)?\b", r"\bstuck\b", r"\bimpeded\b",
    r"\bsteps\b", r"\bprocess\b", r"\bprocedure\b", r"\baction\b",
    r"\brisk acceptance\b", r"\bsign[- ]?off\b", r"\bapproval\b",
    r"\blet me know\b", r"\badvise\b", r"\binform\b", r"\bnotify\b",
    r"\bany update\b", r"\blatest update\b", r"\bprogress\b"
]

COURTESY_ONLY = [
    r"\bthanks?\b", r"\bthank you\b", r"\bthx\b", r"\bty\b",
    r"\bnoted\b", r"\backnowledged\b", r"\back\b", r"\bgot it\b",
    r"\bdone\b", r"\bresolved\b", r"\bfixed\b", r"\bcompleted\b",
    r"\bfyi\b", r"\bfor your information\b", r"\bheads up\b",
    r"\bok\b", r"\bokay\b", r"\balright\b", r"\bsounds good\b",
    r"\blooks good\b", r"\blgtm\b", r"\bapproved\b",
    r"\bno problem\b", r"\bno worries\b", r"\byou're welcome\b"
]

@staticmethod
def needs_response_rule_based(text: str) -> bool:
    if not text:
        return False
    t = " " .join(text.lower().split())

    if any(re.search(p, t) for p in QUESTION_PATTERNS):
        return True

    if len(t) <= 60 and any(re.search(p, t) for p in COURTESY_ONLY):
        return False

    if ("[~" in t or "@" in t) and any(re.search(p, t) for p in QUESTION_PATTERNS):
        return True

    return False