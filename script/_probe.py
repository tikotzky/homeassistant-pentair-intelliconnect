"""Quick API probe — exercises the client and dumps listdevices structure."""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/workspaces/hacs-pentair-pool")
from custom_components.pentair_pool.api.client import PentairPoolApiClient  # noqa: E402
import aiohttp  # noqa: E402

EMAIL = os.environ["EMAIL"]
PASSWORD = os.environ["PASSWORD"]


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = PentairPoolApiClient(EMAIL, PASSWORD, session)
        await client.async_login()
        print("logged in, sub =", client._cognito_sub)
        listing = await client.async_list_devices()
        resp = listing.get("response")
        print("listdevices response type:", type(resp).__name__)
        if isinstance(resp, list):
            print(f"  list len: {len(resp)}")
            for dev in resp[:2]:
                print(f"  device keys: {list(dev)[:10]}")
                print(f"    pname={dev.get('pname')!r}")
                print(f"    deviceType={dev.get('deviceType')!r}")
                print(f"    deviceId={dev.get('deviceId')!r}")
                print(f"    arn={dev.get('arn')!r}")
                # Try fetching its details
                did = dev.get("deviceId") or (dev.get("arn", "") or "").rsplit("/", 1)[-1]
                if did:
                    detail = await client.async_get_device(did)
                    print(f"\n  get_device({did}) keys: {list(detail)}")
                    inner = detail.get("response")
                    print(f"    response type: {type(inner).__name__}")
                    if isinstance(inner, dict):
                        print(f"    response keys: {list(inner)}")
                        data_items = inner.get("data")
                        if isinstance(data_items, list):
                            print(f"    data list len: {len(data_items)}")
                            if data_items:
                                first = data_items[0]
                                print(f"    data[0] keys: {list(first)[:15]}")
                                fields = first.get("fields") or {}
                                print(f"    field count: {len(fields)}")
                                for k in sorted(fields)[:10]:
                                    v = fields[k]
                                    print(f"      {k}: name={v.get('name')!r} value={v.get('value')!r}")
                        else:
                            print(f"    inner.data not list: {type(data_items).__name__}")
                            print(json.dumps(inner, indent=2)[:1200])
                    elif isinstance(inner, list):
                        print(f"    response list len: {len(inner)}")
                        if inner:
                            print(f"    [0] keys: {list(inner[0])[:15]}")
                    else:
                        print(json.dumps(detail, indent=2)[:1500])
        else:
            print(json.dumps(listing, indent=2)[:1500])


asyncio.run(main())
