"""Offline subprocess fixture speaking newline-delimited MCP JSON-RPC."""
import json
import os
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
list_count = 0
calls = 0


def send(value):
    print(json.dumps(value), flush=True)


def tool(name):
    properties = {"query": {"type": "string"}, "region": {"type": "string"}} if name == "map_search_places" else {"uid": {"type": "string"}}
    return {"name": name, "inputSchema": {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}}


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "offline-fixture-" + str(os.getpid()), "version": "1"}}
    elif method == "tools/list":
        list_count += 1
        result = {"tools": [tool("map_search_places"), tool("map_place_details")]}
        if mode == "pages":
            result["nextCursor"] = str(list_count)
        if mode == "schema_large":
            result["tools"][0]["inputSchema"]["description"] = "x" * 300000
        if mode == "drift" and list_count > 1:
            result["tools"][0]["inputSchema"]["properties"]["query"]["minLength"] = 3
    elif method == "tools/call":
        calls += 1
        if mode == "baidu":
            poi = {"name": "颐和园", "city": "北京市", "uid": "uid2", "address": "新建宫门路19号",
                   "detail_info": {"shop_hours": "06:30-18:00",
                                   "detail_url": "https://api.map.baidu.com/place/detail?uid=uid2&output=html"}}
            value = {"results": [poi]} if request["params"]["name"] == "map_search_places" else poi
            send({"jsonrpc": "2.0", "id": request["id"],
                  "result": {"content": [{"type": "text", "text": json.dumps(value)}], "isError": False}})
            continue
        if mode == "timeout":
            time.sleep(30)
        if mode == "eof":
            break
        if mode == "notifications":
            send({"jsonrpc": "2.0", "method": "notifications/message",
                  "params": {"level": "info", "data": "notification-secret"}})
            print("stderr-secret" * 10000, file=sys.stderr, flush=True)
        result = {"content": [{"type": "text", "text": json.dumps(
            {"pid": os.getpid(), "calls": calls, "text": "x" * 70000 if mode == "large" else "ok"})}],
                  "isError": mode == "tool_error"}
    else:
        result = {}
    send({"jsonrpc": "2.0", "id": request["id"], "result": result})
