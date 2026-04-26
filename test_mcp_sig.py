from mcp.server.fastmcp import FastMCP
mcp = FastMCP("test")
try:
    print("Attempting mcp.run(transport='http', host='0.0.0.0', port=8000)")
    # We don't actually want it to block, so we just check if it exists or signature
    import inspect
    print(f"mcp.run signature: {inspect.signature(mcp.run)}")
except Exception as e:
    print(f"Error: {e}")
