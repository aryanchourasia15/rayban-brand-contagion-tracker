"""
Quick GDELT fetch with 15s timeout — returns raw JSON for the audit.
Quotes the query so GDELT handles hyphens correctly.
"""
import json
import sys
import requests
from datetime import datetime, timedelta, timezone

end_dt   = datetime.now(timezone.utc)
start_dt = end_dt - timedelta(days=30)

fmt = "%Y%m%d%H%M%S"
params = {
    "query":          '"Ray-Ban Meta"',
    "mode":           "artlist",
    "format":         "json",
    "maxrecords":     "10",
    "sort":           "DateDesc",
    "startdatetime":  start_dt.strftime(fmt),
    "enddatetime":    end_dt.strftime(fmt),
}

url = "https://api.gdeltproject.org/api/v2/doc/doc"
headers = {"User-Agent": "RayBanCustomerTrustIntelligence/1.0 (Academic Research; HEC Paris)"}

try:
    r = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        articles = data.get("articles", [])
        print(f"Articles returned: {len(articles)}")
        for i, a in enumerate(articles, 1):
            print(f"\n  [{i}] title: {a.get('title', '')[:80]}")
            print(f"       url  : {a.get('url', '')[:80]}")
            print(f"       date : {a.get('seendate', '')}")
            print(f"       domain: {a.get('domain', '')}")
    else:
        print(r.text[:300])
except Exception as e:
    print(f"ERROR: {e}")
