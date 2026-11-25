from pathlib import Path
p = Path("keel/src/keel/webapp.py")
t = p.read_text(encoding="utf-8")
old = '''        if length > limit:
            self._send_json({"error": too_large},
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None'''
new = '''        if length > limit:
            # Drain (a bounded amount of) the oversized body before answering.
            # Responding while the client is still writing makes some Windows
            # clients see a reset connection instead of the 413 response.
            try:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 64 * 1024))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except (OSError, ValueError):
                pass
            self._send_json({"error": too_large},
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None'''
assert old in t
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("drain oversized body before 413")
