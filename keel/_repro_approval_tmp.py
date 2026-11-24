import sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, "src")
from keel.permission_contracts import ApprovalStore, ApprovalRequest, ApprovalReply

for round_no in range(5):
    tmp = tempfile.mkdtemp(prefix="approval-repro-")
    store = ApprovalStore(tmp, "project-a")
    count = 12
    errors = []
    def worker(i):
        try:
            own = ApprovalStore(tmp, "project-a")
            own.decide(ApprovalRequest("execute", f"cmd{i}", f"cmd{i}*"),
                       ApprovalReply.ALWAYS)
        except BaseException as exc:
            errors.append(exc)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)
    saved = len(store.saved_patterns())
    print("round", round_no, "saved", saved, "of", count, "errors", len(errors))
