# 🤖 Agent Integration Guide

This guide covers how to integrate mcp-webgate with CLI-based AI agents that support the Model Context Protocol (MCP).

> **Claude Desktop** is an IDE-class integration and is documented in the [IDE Integration Guide](./IDE.md).

---

## 🔧 Prerequisites

Make sure you have `uvx` available:

```bash
pip install uv
```

You also need a [search backend](../../README.md#backends). The easiest option is SearXNG running locally:

```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```

No Docker? Use a cloud backend — see [Backends](../../README.md#backends) for Brave, Tavily, Exa, and SerpAPI.

---

## ♊ Gemini CLI

Google's command-line interface for Gemini AI.

### Prerequisites

- **Gemini CLI** installed ([Installation Guide](https://github.com/google-gemini/gemini-cli))
- Gemini CLI version with MCP support

### Configuration

Gemini CLI reads MCP servers from `~/.gemini/config.json`:

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

### Configuration options

**With a cloud backend:**
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

**With LLM summarization (using CLI args — integers stay integers):**
```json
{
  "mcpServers": {
    "webgate": {
      "command": "uvx",
      "args": [
        "mcp-webgate",
        "--searxng-url", "http://localhost:8080",
        "--llm-enabled",
        "--llm-base-url", "http://localhost:11434/v1",
        "--llm-model", "gemma3:27b",
        "--llm-timeout", "60"
      ]
    }
  }
}
```

### Usage

```bash
# Start Gemini CLI — webgate loads automatically from config
gemini

# Or pass it explicitly (check your Gemini CLI version for the exact flag)
gemini --mcp-servers webgate
```

Once started, use webgate through natural language:

```
Search the web for: Python packaging best practices 2024
```

```
Fetch the content of https://peps.python.org/pep-0517/
```

### 🔍 Troubleshooting

**MCP server not loading:**
1. Check Gemini CLI version supports MCP
2. Validate `~/.gemini/config.json` JSON syntax: `python3 -m json.tool < ~/.gemini/config.json`
3. Test uvx: `uvx mcp-webgate --help`

**"command not found":**
```json
{
  "command": "/Users/yourname/.local/bin/uvx"
}
```

---

## 💻 Claude CLI

Anthropic's command-line interface for Claude AI.

### Prerequisites

- **Claude CLI** installed
- Claude CLI version with MCP support

### Configuration

Claude CLI typically accepts MCP servers via command-line flags. Create a shell alias or wrapper for convenience:

**Option 1: Direct flag**
```bash
claude --mcp-servers webgate
```

**Option 2: Shell alias using CLI args** (add to `~/.bashrc`, `~/.zshrc`, or equivalent)
```bash
alias claude-web='claude --mcp-servers webgate'
```

**Option 3: Wrapper script** (`~/bin/claude-web`)
```bash
#!/bin/bash
# claude-web — Claude CLI with webgate (config via CLI args, no env vars needed)

exec claude --mcp-servers webgate \
  --server-args mcp-webgate \
  --server-args "--searxng-url" \
  --server-args "http://localhost:8080" \
  "$@"
```

Or using env vars in the wrapper:
```bash
#!/bin/bash
export WEBGATE_DEFAULT_BACKEND="${WEBGATE_DEFAULT_BACKEND:-searxng}"
export WEBGATE_SEARXNG_URL="${WEBGATE_SEARXNG_URL:-http://localhost:8080}"

exec claude --mcp-servers webgate "$@"
```

```bash
chmod +x ~/bin/claude-web
```

### 🐚 Shell profile locations

| Platform | File |
|---|---|
| macOS / Linux (bash) | `~/.bashrc` or `~/.bash_profile` |
| macOS / Linux (zsh) | `~/.zshrc` |
| Windows (PowerShell) | `$PROFILE` |
| Windows (cmd) | System → Environment Variables |

### Usage

```bash
# Using wrapper
claude-web "What are the latest changes to the Python packaging ecosystem?"

# Or directly
claude --mcp-servers webgate "Fetch and summarize https://packaging.python.org/en/latest/"
```

### 🔍 Troubleshooting

**Claude CLI doesn't recognize `--mcp-servers`**: Update to the latest version; flag name may vary (`--mcp`, etc.).

**Permission issues:**
```bash
chmod +x ~/bin/claude-web
export PATH="$HOME/bin:$PATH"
```

---

## 🔧 Using webgate with local or smaller models

If your model ignores webgate and falls back to a built-in fetch tool, see [Using webgate with local or smaller models](../../README.md#local-models) in the main README for a ready-to-use system prompt you can add to your agent configuration.

---

## 🔍 Troubleshooting Common Issues

### "command not found" / uvx not in PATH

```bash
# Find uvx path
which uvx

# Use full path in config
{
  "command": "/Users/yourname/.local/bin/uvx"
}

# Or add to PATH permanently
export PATH="$HOME/.local/bin:$PATH"
```

### Backend not responding

```bash
# Test SearXNG
curl "http://localhost:8080/search?q=test&format=json"
```

### JSON syntax errors

```bash
python3 -m json.tool < ~/.gemini/config.json
```

### MCP server crashes at startup

```bash
# Run directly to see error output and available options
uvx mcp-webgate --help
```

---

**Next steps**: [IDE Integration](./IDE.md) · [Full Configuration](../../README.md#full-configuration) · [Backends](../../README.md#backends)
