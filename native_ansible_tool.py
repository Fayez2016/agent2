# This file is deprecated. Ansible tools have been moved to a dedicated MCP server.
# See ansible_mcp_server.py and docker-compose.yml for details.

import logging
tool_logger = logging.getLogger("AnsibleTool")

def deprecated_notice():
    tool_logger.warning("Built-in Ansible tools are deprecated. Use the 'ansible' MCP toolset instead.")

if __name__ == "__main__":
    deprecated_notice()
