import httpx
r = httpx.get("http://127.0.0.1:6907/api/browser/proxy?url=https://example.com", timeout=10)
body = r.text
if 'var P="/api/browser/proxy?url="' in body:
    print("SCRIPT FOUND")
else:
    print("SCRIPT NOT FOUND")
# show the injected part
idx = body.find("<script>")
if idx >= 0:
    print("--- injected script ---")
    print(body[idx:idx+600])
