from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
import httpx

# Initialize FastMCP server
mcp = FastMCP("my-company-api")

# HTML for the homepage that displays "MCP Server"
async def homepage(request: Request) -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MCP Server</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            h1 {
                margin-bottom: 10px;
            }
            button {
                background-color: #f8f8f8;
                border: 1px solid #ccc;
                padding: 8px 16px;
                margin: 10px 0;
                cursor: pointer;
                border-radius: 4px;
            }
            button:hover {
                background-color: #e8e8e8;
            }
            .status {
                border: 1px solid #ccc;
                padding: 10px;
                min-height: 20px;
                margin-top: 10px;
                border-radius: 4px;
                color: #555;
            }
        </style>
    </head>
    <body>
        <h1>MCP Server</h1>
        
        <p>Server is running correctly!</p>
        
        <button id="connect-button">Connect to SSE</button>
        
        <div class="status" id="status">Connection status will appear here...</div>
        
        <script>
            document.getElementById('connect-button').addEventListener('click', function() {
                // Redirect to the SSE connection page or initiate the connection
                const statusDiv = document.getElementById('status');
                
                try {
                    const eventSource = new EventSource('/sse');
                    
                    statusDiv.textContent = 'Connecting...';
                    
                    eventSource.onopen = function() {
                        statusDiv.textContent = 'Connected to SSE';
                    };
                    
                    eventSource.onerror = function() {
                        statusDiv.textContent = 'Error connecting to SSE';
                        eventSource.close();
                    };
                    
                    eventSource.onmessage = function(event) {
                        statusDiv.textContent = 'Received: ' + event.data;
                    };
                    
                    // Add a disconnect option
                    const disconnectButton = document.createElement('button');
                    disconnectButton.textContent = 'Disconnect';
                    disconnectButton.addEventListener('click', function() {
                        eventSource.close();
                        statusDiv.textContent = 'Disconnected';
                        this.remove();
                    });
                    
                    document.body.appendChild(disconnectButton);
                    
                } catch (e) {
                    statusDiv.textContent = 'Error: ' + e.message;
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

# Create Starlette application with SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage),  # Add the homepage route
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

@mcp.tool()
async def get_company_data(resource_id: str) -> str:
    """Get data from your company API.
    
    Args:
        resource_id: The ID of the resource to fetch
    """
    # Implement your API call here
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.your-company.com/data/{resource_id}",
            headers={"Authorization": "Bearer YOUR_API_KEY"}
        )
        response.raise_for_status()
        return response.text()

if __name__ == "__main__":
    mcp_server = mcp._mcp_server
    
    # Create and run Starlette app
    starlette_app = create_starlette_app(mcp_server, debug=True)
    uvicorn.run(starlette_app, host="0.0.0.0", port=8080)