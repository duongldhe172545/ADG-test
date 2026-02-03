# NotebookLM MCP Server for Antigravity

This repository contains the configuration and workflows to set up the **NotebookLM MCP Server** for use with **Antigravity**, **Opencode** (and other MCP clients).

It specifically addresses and fixes the "invalid trailing data" error caused by the startup banner of the `notebooklm-mcp-server` package.

## Features

- **Automated Setup Workflow**: A comprehensive workflow (`.agent/workflows/setup-notebooklm-mcp.md`) to install and configure the server.
- **Banner Suppression Fix**: Includes a wrapper script (`run_mcp.py`) that filters out the ASCII art banner from `stdout`, ensuring clean JSON-RPC communication.
- **Antigravity Integration**: Ready-to-use configuration for Antigravity's `mcp_config.json`.

## Prerequisites

- Python 3.10+
- `pip`
- An active Google account with access to [NotebookLM](https://notebooklm.google.com/)

## Installation

You can use the provided workflow in Antigravity or follow these manual steps:

1.  **Install the package**:
    ```bash
    pip install notebooklm-mcp-server
    ```

2.  **Clone this repository** (or copy the files) to your desired location (e.g., `d:\antigravity\notebooklm`).

3.  **Authenticate**:
    ```bash
    notebooklm-mcp-auth
    ```
    Follow the browser prompts to log in.

4.  **Configure Antigravity**:
    Add the following to your `C:\Users\Administrator\.gemini\antigravity\mcp_config.json`:

    ```json
    {
      "mcpServers": {
        "notebooklm-mcp-server": {
          "command": "python",
          "args": [
            "-u",
            "-W",
            "ignore",
            "d:\\antigravity\\notebooklm\\run_mcp.py"
          ],
          "env": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONWARNINGS": "ignore"
          }
        }
      }
    }
    ```
    *Note: Adjust the path to `run_mcp.py` if you placed it elsewhere.*

5.  **Reload Antigravity**:
    Restart the application or reload the window (`Ctrl+Shift+P` -> `Developer: Reload Window`).

## Usage

Once configured, you can use Antigravity to interact with your NotebookLM notebooks.

- **List Notebooks**: Ask "List my notebooks"
- **Query Notebooks**: Ask questions about your documents.
- **Add Sources**: Add URLs or text to your notebooks.

## Troubleshooting

### "Invalid trailing data" Error
This error occurs when the server prints non-JSON text (like a banner) to `stdout`. The included `run_mcp.py` script fixes this by intercepting `stdout` and removing the banner. Ensure your config points to this script, not the module directly.

### Authentication Issues
If you see auth errors, try running `notebooklm-mcp-auth` again and ensure you complete the login process in the browser.

## Files

- `run_mcp.py`: Wrapper script to suppress the startup banner.
- `.agent/workflows/setup-notebooklm-mcp.md`: Antigravity workflow for automated setup.
- `list_notebooks.py`: Utility script to list notebooks (for testing).
