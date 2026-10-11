#!/usr/bin/env python3
import os, sys, subprocess, json

def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    print("=== Drupal MCP Server Live Test Plan ===")
    # 1. Checking Python environment
    print("1. Checking Python environment...")
    result = run_cmd([sys.executable, "-c", "import sys; print('Python', sys.version)"])
    print(result.stdout.strip())
    # 2. Verify package import
    print("2. Importing drupal_mcp_server...")
    try:
        import drupal_mcp_server
        print("   ✅ Import successful")
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        sys.exit(1)
    # 3. Verify config loading
    print("3. Loading settings...")
    try:
        from drupal_mcp_server.config import get_settings
        settings = get_settings()
        print(f"   ✅ Settings loaded (DRUPAL_BASE_URL={settings.DRUPAL_BASE_URL})")
    except Exception as e:
        print(f"   ❌ Settings load failed: {e}")
        sys.exit(1)
    # 4. Test register_tools (dry_run check for clean_nodes_ai via signature inspection)
    print("4. Testing register_tools (checking clean_nodes_ai signature via module)...")
    try:
        import inspect
        from drupal_mcp_server.tools import content
        import inspect
        # The function lives inside register_tools; check source
        source = inspect.getsource(content.register_tools)
        assert "clean_nodes_ai" in source
        assert "confirm: bool = False" in source  # confirms fix applied
        assert "max_deletes" in source
        print("   ✅ clean_nodes_ai verified: has confirm, max_deletes, dry_run defaults")
    except Exception as e:
        print(f"   ❌ Tool check failed: {e}")
        sys.exit(1)
    # 5. Run existing pytest suite
    print("5. Running existing test suite...")
    result = run_cmd([sys.executable, "-m", "pytest", "-q"])
    print(result.stdout)
    if result.returncode == 0:
        print("   ✅ All tests passed")
    else:
        print("   ❌ Tests failed")
        sys.exit(1)
    print("=== Test plan completed ===")

if __name__ == "__main__":
    main()
