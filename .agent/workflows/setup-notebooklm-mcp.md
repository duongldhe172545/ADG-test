---
description: Cài đặt và cấu hình NotebookLM MCP Server cho Antigravity (Fix lỗi banner)
---

# Hướng dẫn cài đặt NotebookLM MCP Server

Workflow này sẽ tự động cài đặt và cấu hình NotebookLM MCP Server, bao gồm cả việc xử lý lỗi "invalid trailing data" do banner khởi động của server gây ra.

## Bước 1: Cài đặt package notebooklm-mcp-server

// turbo
```bash
pip install notebooklm-mcp-server
```

## Bước 2: Tạo Wrapper Script để sửa lỗi Banner

NotebookLM MCP Server mặc định in ra một banner ASCII art khi khởi động, điều này làm hỏng giao thức JSON-RPC của MCP. Chúng ta cần tạo một script Python để lọc bỏ banner này.

Tạo file `d:\antigravity\notebooklm\run_mcp.py`:

// turbo
```python
import sys
import io

# Simple delegation approach
class SimpleFilteredStdout:
    def __init__(self, original):
        self.original = original
        # Copy encoding if available, otherwise default to utf-8
        self.encoding = getattr(original, 'encoding', 'utf-8')
        
    def write(self, s):
        # Filter out banner lines
        if any(c in s for c in ['╭', '│', '╰', '─']):
            return len(s)
        if "FastMCP server" in s:
            return len(s)
        return self.original.write(s)
        
    def flush(self):
        if hasattr(self.original, 'flush'):
            self.original.flush()
        
    def __getattr__(self, name):
        return getattr(self.original, name)

# Patch stdout BEFORE importing notebooklm_mcp.server
# because FastMCP initializes at module level
original_stdout = sys.stdout
sys.stdout = SimpleFilteredStdout(original_stdout)

from notebooklm_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
```

Bạn có thể sử dụng tool `write_to_file` để tạo file này.

## Bước 3: Thêm cấu hình MCP Server vào Antigravity

Cập nhật file cấu hình MCP tại `C:\Users\Administrator\.gemini\antigravity\mcp_config.json` để sử dụng wrapper script vừa tạo.

// turbo
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

*Lưu ý: Giữ nguyên các server khác nếu có (ví dụ: firebase-mcp-server).*

## Bước 4: Cập nhật OpenCode Config (Tùy chọn)

Để tránh xung đột hoặc lỗi validate trong OpenCode, hãy đảm bảo `C:\Users\Administrator\.config\opencode\opencode.json` **KHÔNG** chứa cấu hình `mcp` cho NotebookLM, vì Antigravity đã tự quản lý nó qua `mcp_config.json`.

## Bước 5: Xác thực với NotebookLM

> [!IMPORTANT]
> **YÊU CẦU NGƯỜI DÙNG ĐĂNG NHẬP**
> 
> Chạy lệnh sau để mở trình duyệt và đăng nhập vào tài khoản Google/NotebookLM của bạn:

```bash
notebooklm-mcp-auth
```

**Hướng dẫn:**
1. Trình duyệt Chrome sẽ tự động mở với trang NotebookLM
2. Đăng nhập vào tài khoản Google của bạn (nếu chưa đăng nhập)
3. Đợi cho đến khi thấy thông báo "Authentication successful" trong terminal
4. Credentials sẽ được lưu tự động cho các lần sử dụng sau

## Bước 6: Reload Antigravity

> [!IMPORTANT]
> **YÊU CẦU RELOAD ANTIGRAVITY**
> 
> Sau khi hoàn tất xác thực và cấu hình, người dùng cần reload Antigravity để load MCP server mới:
> - Nhấn `Ctrl+Shift+P`
> - Gõ "Developer: Reload Window"
> - Nhấn Enter

## Bước 7: Xác nhận cài đặt thành công

Sau khi reload, kiểm tra xem NotebookLM MCP server đã được load thành công bằng cách sử dụng các công cụ NotebookLM trong Antigravity (ví dụ: hỏi về danh sách notebooks).

---

## Thông tin thêm

- **Package**: `notebooklm-mcp-server`
- **Wrapper Script**: `d:\antigravity\notebooklm\run_mcp.py`
- **Config file**: `C:\Users\Administrator\.gemini\antigravity\mcp_config.json`
- **Auth command**: `notebooklm-mcp-auth`
