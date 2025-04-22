import asyncio
import websockets
import os

async def echo(websocket, path=None):
    try:
        async for message in websocket:
            print(f"Received message: {message}")
            
            # Replace '||' with newline and save to app_betea/input/mess_websocket.txt
            processed_message = message.replace('||', '\n')
            
            with open('app_betea/input/mess_websocket.txt', 'w') as file:
                file.write(processed_message)
            
            await websocket.send(f"Server received and processed: {message}")
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed")
    except Exception as e:
        print(f"Unexpected error: {e}")

async def main():
    server = await websockets.serve(
        echo, 
        host="0.0.0.0", 
        port=8765,
        ping_interval=20,
        ping_timeout=20
    )
    
    print(f"WebSocket server started on ws://0.0.0.0:8765")
    print(f"Messages will be saved to {os.path.abspath('app_betea/input/mess_websocket.txt')}")
    
    # Keep server running
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())