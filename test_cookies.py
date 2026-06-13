from curl_cffi import requests
session = requests.Session()
session.cookies.set("foo", "bar", domain="example.com")
print(type(session.cookies))
print("iter:", list(session.cookies))
print("items:", list(session.cookies.items()))
if hasattr(session.cookies, "jar"):
    print("jar iter:", list(session.cookies.jar))
