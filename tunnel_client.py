import asyncio
import random
import string
import socket

def generate_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# 客户端随机生成用户 ID
USER_ID = generate_id()
# USER_ID = 'xxxxxxxx'
SERVER_IP = "113.206.134.78"    # 根据需要修改为实际服务器 IP
TUNNEL_PORT = 59854
LOCAL_HTTP_PORT = 45678

def set_keepalive(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    """设置 TCP Keep-Alive 选项"""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

async def async_pipe(reader, writer):
    """异步管道：不断读取数据并写入目标连接"""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        print("管道传输错误:", e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def handle_tunnel(tunnel_reader, tunnel_writer):
    """
    当隧道建立成功后，通过该连接转发数据，
    同时连接本地 HTTP 服务，将隧道与本地服务做双向数据转发
    """
    try:
        # 建立到本地 HTTP 服务的连接
        local_reader, local_writer = await asyncio.open_connection("127.0.0.1", LOCAL_HTTP_PORT)
        # 同时启动两个协程任务，实现双向数据转发
        task1 = asyncio.create_task(async_pipe(tunnel_reader, local_writer))
        task2 = asyncio.create_task(async_pipe(local_reader, tunnel_writer))
        await asyncio.gather(task1, task2)
    except Exception as e:
        print("隧道处理错误:", e)
    finally:
        tunnel_writer.close()
        try:
            await tunnel_writer.wait_closed()
        except Exception:
            pass

async def tunnel_worker():
    """
    隧道协程：不断建立到服务器隧道端口的连接，
    发送 "TUNNEL <USER_ID>" 握手后进入数据转发处理
    """
    while True:
        try:
            tunnel_reader, tunnel_writer = await asyncio.open_connection(SERVER_IP, TUNNEL_PORT)
            # 设置底层 socket 的 keepalive 选项
            sock = tunnel_writer.get_extra_info("socket")
            if sock is not None:
                set_keepalive(sock)
            handshake = f"TUNNEL {USER_ID}\n"
            tunnel_writer.write(handshake.encode())
            await tunnel_writer.drain()
            print("已建立一条隧道连接")
            # 处理隧道转发
            await handle_tunnel(tunnel_reader, tunnel_writer)
        except Exception as e:
            print("隧道任务错误:", e)
        # 连接出现错误或隧道关闭后等待一秒后重试
        await asyncio.sleep(1)


async def heartbeat_worker():
    """
    隧道协程：建立心跳连接，
    发送 "REGISTER <USER_ID>" 握手后进入数据转发处理
    """
    tunnel_reader, tunnel_writer = await asyncio.open_connection(SERVER_IP, TUNNEL_PORT)
    # 设置底层 socket 的 keepalive 选项
    sock = tunnel_writer.get_extra_info("socket")
    handshake = f"HEART {USER_ID}\n"
    tunnel_writer.write(handshake.encode())
    await tunnel_writer.drain()

    if sock is not None:
        set_keepalive(sock)
    while True:
        try:
            tunnel_writer.write(handshake.encode())
            await tunnel_writer.drain()
        except Exception as e:
            print("隧道任务错误:", e)
        # 连接出现错误或隧道关闭后等待一秒后重试
        await asyncio.sleep(1)

async def main():
    print("客户端启动，用户 ID:", USER_ID)
    print(f"文件访问地址: http://{SERVER_IP}:57487/{USER_ID}/")
    print(f"psychopy访问地址: http://{SERVER_IP}:57487/{USER_ID}/index.html")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER_IP, TUNNEL_PORT))
    s.send(f"REGISTER {USER_ID}\n".encode())
    data = s.recv(1024).decode()
    if data == 'SUCCESS':
        asyncio.create_task(heartbeat_worker())
        # 根据需要启动多个隧道协程任务，这里只启动了 1 个
        tasks = [asyncio.create_task(tunnel_worker()) for _ in range(1)]
        await asyncio.gather(*tasks)
    else:
        print('！！！')
if __name__ == "__main__":

    asyncio.run(main())

