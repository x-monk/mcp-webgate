# 🖥️ IDE Integration Guide

This guide covers how to integrate mcp-webgate with IDEs and desktop AI clients that support the Model Context Protocol (MCP).

## 🔧 Prerequisites

Before configuring any IDE, make sure you have `uvx` available:

```bash
pip install uv
```

`uvx` runs mcp-webgate without a permanent install. You only need to do this once.

You also need a [search backend](../../README.md#backends). The easiest option is SearXNG running locally:

```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

No Docker? Use a cloud backend instead — see [Backends](../../README.md#backends) for Brave, Tavily, Exa, and SerpAPI.

---

## 🖥️ Claude Desktop

Anthropic's desktop application for Claude AI.

### Configuration

Open the config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the `webgate` server:

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

**After editing**: completely quit and restart Claude Desktop (Cmd+Q on macOS — don't just close the window).

### With a cloud backend

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "brave", "--brave-api-key", "BSA..."]
    }
  }
}
```

### With LLM summarization

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": [
        "mcp-webgate",
        "--default-backend", "searxng",
        "--searxng-url", "http://localhost:8080",
        "--llm-enabled",
        "--llm-base-url", "http://localhost:11434/v1",
        "--llm-model", "gemma3:27b"
      ]
    }
  }
}
```

### 🔍 Troubleshooting

**"spawn uvx ENOENT"**: Claude Desktop has a restricted PATH. Use the full path to uvx:

```bash
which uvx
# Returns: /Users/yourname/.local/bin/uvx
```

```json
{
  "mcpServers": {
    "webgate": {
      "command": "/Users/yourname/.local/bin/uvx",
      "args": ["mcp-webgate"],
      "env": { "..." : "..." }
    }
  }
}
```

**Configuration not taking effect**: Completely quit Claude Desktop (Cmd+Q), wait a few seconds, then reopen.

---

## 💻 Claude Code

Anthropic's CLI-based coding agent (this tool).

### Configuration

Create `.mcp.json` in your project folder:

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

For a global config (all projects), place the file in your home directory: `~/.mcp.json`.

### Usage

Once configured, Claude Code can use webgate automatically:

```
Search the web for: Python async patterns best practices 2024
```

```
Fetch the content of https://docs.python.org/3/library/asyncio.html
```

---

## ⚡ Zed Editor

High-performance, multiplayer code editor with native MCP support.

### Configuration

Open Settings (`Cmd+,` on macOS / `Ctrl+,` on Linux/Windows) and add to `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

> **Note**: Zed uses `"context_servers"` (not `"mcpServers"`) and requires a nested `"command"` object.

### Where to save configuration

- **User-level**: `~/.config/zed/settings.json` — affects all projects

### 🔍 Troubleshooting

**Server not appearing:**
1. Check Zed version supports MCP context servers
2. Verify `~/.config/zed/settings.json` has valid JSON syntax
3. Restart Zed after config changes

**Windows note**: If `uvx` is not found, use the full path (e.g. `C:/Users/you/AppData/Local/Programs/Python/Python312/Scripts/uvx.exe`).

---

## 🖱️ Cursor

AI-powered code editor. MCP tools require **Agent mode**.

### Configuration

Create or edit `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

For global configuration (all projects), create `~/.cursor/mcp.json`.

### Usage with Agent mode

MCP tools only work in **Agent mode**:

1. Open Cursor Chat
2. Click the mode selector at the bottom of the chat panel
3. Select **Agent** mode
4. Now you can use webgate:

```
Search the web for recent changes to the React hooks API
```

### 🔍 Troubleshooting

**Tools not appearing**: Ensure you're in **Agent mode** (not Chat or Composer mode). Restart Cursor after configuration changes.

---

## 🌊 Windsurf

Modern code editor with AI integration.

### Configuration

Windsurf uses a single global configuration file:

- **macOS/Linux**: `~/.codeium/windsurf/mcp_config.json`
- **Windows**: `C:\Users\<username>\.codeium\windsurf\mcp_config.json`

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

> **Note**: Windsurf does not support project-specific MCP configuration. All servers are configured globally.

### 🔍 Troubleshooting

**Configuration not loading**: Restart Windsurf completely (not just reload window). Verify the file is at the correct OS-specific path.

---

## 🔷 VSCode

Visual Studio Code via GitHub Copilot Chat (VS Code 1.99+) or a standalone MCP extension.

### Prerequisites

- **VS Code 1.99+** (1.100+ recommended for the stable GA build)
- GitHub Copilot Chat with a tool-call capable model, **or** the [MCP for VS Code](https://marketplace.visualstudio.com/search?term=MCP&target=VSCode) extension

### Configuration

Create `.vscode/mcp.json` in your workspace root:

```json
{
  "servers": {
    "webgate": {
      "command": "uvx",
      "args": ["mcp-webgate", "--default-backend", "searxng", "--searxng-url", "http://localhost:8080"]
    }
  }
}
```

> **Note**: VS Code uses the key `"servers"` (not `"mcpServers"`).

For user-level configuration (all workspaces), open the Command Palette (`Cmd/Ctrl+Shift+P`) and run **`MCP: Open User Configuration`**.

### Starting the server

1. Open Command Palette (`Cmd/Ctrl+Shift+P`)
2. Run: **MCP: List Servers**
3. Find `webgate` and click **Start**

### Usage with GitHub Copilot

MCP tools work in **Agent mode**:

1. Open Copilot Chat (`Cmd/Ctrl+Shift+I`)
2. Switch to **Agent** mode or use the `@workspace` prefix
3. Use webgate:

```
@workspace Search the web for the latest TypeScript 5.x release notes
```

### 🔍 Troubleshooting

**MCP servers not available**: Check VS Code version is 1.99+. Run **MCP: List Servers** from the Command Palette to inspect status.

**Tools not appearing**: Must use Agent mode or `@workspace` prefix. Run **MCP: Restart Server** if needed.

---

## 🖥️ Multi-instance setup (CLI args)

Running webgate in multiple IDEs simultaneously (e.g. Zed + Cursor)? Use **CLI arguments** instead of env vars. Each instance gets its own config without conflicts — and integers stay integers, no string-wrapping needed.

**Precedence**: `args > env vars > webgate.toml > defaults`

```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": [
        "mcp-webgate",
        "--searxng-url", "http://localhost:8080",
        "--llm-enabled",
        "--llm-model", "gemma3:27b",
        "--llm-timeout", "60"
      ]
    }
  }
}
```

Boolean flags: `--llm-enabled` / `--no-llm-enabled`, `--debug` / `--no-debug`, etc.

Full reference: `uvx mcp-webgate --help`

---

## 🔍 Troubleshooting Common Issues

### "command not found" / "spawn ENOENT"

1. Verify uvx is installed: `uvx --version`
2. Find the full path: `which uvx` (macOS/Linux) or `where uvx` (Windows)
3. Use the full path in your config:
   ```json
   { "command": "/Users/yourname/.local/bin/uvx" }
   ```
4. Add uvx to PATH: `export PATH="$HOME/.local/bin:$PATH"`

### JSON syntax errors

```bash
python3 -m json.tool < config.json
```

### Backend not responding

```bash
# Test SearXNG
curl http://localhost:8080/search?q=test&format=json

# Test webgate directly
uvx mcp-webgate --help
```

### Config file locations

| Client | Config path |
|--------|-------------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `.mcp.json` in project root (or `~/.mcp.json` global) |
| Zed | `~/.config/zed/settings.json` |
| Cursor (project) | `.cursor/mcp.json` |
| Cursor (global) | `~/.cursor/mcp.json` |
| Windsurf (macOS/Linux) | `~/.codeium/windsurf/mcp_config.json` |
| Windsurf (Windows) | `C:\Users\<username>\.codeium\windsurf\mcp_config.json` |
| VSCode (workspace) | `.vscode/mcp.json` |

---

**Next steps**: [Agent Integration](./AGENT.md) · [Full Configuration](../../README.md#full-configuration) · [Backends](../../README.md#backends)
