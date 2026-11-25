import sqlite3
c = sqlite3.connect(":memory:")
body = '{"status":"pending","question":"q"}'
print("json_type  =", c.execute("SELECT json_type(?, '$.status')", (body,)).fetchone()[0])
print("json_extract =", c.execute("SELECT json_extract(?, '$.status')", (body,)).fetchone()[0])
print("match type test =", c.execute("SELECT count(*) FROM (SELECT ? AS body) WHERE json_type(body,'$.status')='\"pending\"'", (body,)).fetchone()[0])
