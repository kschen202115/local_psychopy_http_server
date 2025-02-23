import asyncio
import socket

# 全局：用户ID -> 隧道连接池（队列），存储 (reader, writer, event)
tunnel_pools = {}
pool_lock = asyncio.Lock()

def set_keepalive(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

async def add_tunnel(user_id, tunnel_info):
    async with pool_lock:
        if user_id not in tunnel_pools:
            print(f"用户 {user_id} 不存在")
            reader, writer, event =tunnel_info
            writer.close()
            await writer.wait_closed()
        await tunnel_pools[user_id].put(tunnel_info)
        print(f"用户 {user_id} 的隧道连接已加入池中。")

async def get_tunnel(user_id):
    while True:
        async with pool_lock:
            if user_id in tunnel_pools and not tunnel_pools[user_id].empty():
                return await tunnel_pools[user_id].get()
            if user_id not in tunnel_pools:
                return None
        await asyncio.sleep(1)  # 短暂休眠，避免忙等待

async def remove_tunnel(user_id, reader=None, writer=None):
    """注销用户ID，从连接池中移除，并关闭连接"""
    async with pool_lock:
        if user_id in tunnel_pools:
            del tunnel_pools[user_id]
            print(f"用户 {user_id} 已注销")
            # 关闭连接
            if writer:
                writer.close()
                await writer.wait_closed()
            if reader:
                # 尝试读取剩余的数据，避免阻塞
                try:
                    await reader.read(1)
                except:
                    pass
                finally:
                    reader.feed_eof() # 确保reader完成
                    await reader.wait_closed()

async def heartbeat_check(user_id, reader, writer):
    """心跳检测，如果连接断开则注销用户"""
    addr = writer.get_extra_info('peername')
    
    while True:
        await asyncio.sleep(1)
        try:
            # 尝试读取一个字节的数据，如果连接断开会抛出异常
            data = await reader.read(1024)
            if not data:
                print(f"用户 {user_id} 连接断开 (心跳检测)")
                await remove_tunnel(user_id, reader, writer)
                break  # 连接断开
        except Exception as e:
            print(f"用户 {user_id} 心跳检测异常: {e}")
            await remove_tunnel(user_id, reader, writer)
            break # 连接断开
        await asyncio.sleep(1)  # 等待一段时间后再次检测
        
async def handle_tunnel_connection(reader, writer):
    addr = writer.get_extra_info('peername')
    sock = writer.get_extra_info('socket')
    if sock:
        set_keepalive(sock)
    try:
        initial_data = await reader.read(1024)
        if not initial_data:
            writer.close()
            await writer.wait_closed()
            return
        parts = initial_data.decode().split()
        print(parts)
        if len(parts) < 2:
            writer.close()
            await writer.wait_closed()
            return
        user_id = parts[1]
        if parts[0] == 'HEART':
            asyncio.create_task(heartbeat_check(user_id, reader, writer))
        if parts[0] == 'REGISTER':
            async with pool_lock:
                if user_id not in tunnel_pools:
                    tunnel_pools[user_id] = asyncio.Queue()
                    print(f'{user_id}注册成功')
                    writer.write('SUCCESS'.encode())

                else:
                    print(f'{user_id}注册失败，已存在')
                    writer.write('FAIL'.encode())
                writer.close()
                await writer.wait_closed()
                return
        if parts[0] == 'TUNNEL':
            event = asyncio.Event()  # 创建一个 Event 对象
            await add_tunnel(user_id, (reader, writer, event)) #  将 event 对象加入隧道信息
            print(f"用户 {user_id} 的隧道连接已加入池中，等待 HTTP 请求...")

            await event.wait()  # 等待 Event 对象被设置
            print(f"隧道 {addr} 收到关闭信号，即将关闭")

    except Exception as e:
        print(f"处理隧道连接错误 {addr}: {e}")
    # finally:
        writer.close()
        await writer.wait_closed()
        print(f"隧道连接已关闭 {addr}")

async def async_pipe(reader, writer):
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

async def handle_http_connection(reader, writer):
    addr = writer.get_extra_info('peername')
    print("接收到 HTTP 请求，来自", addr)
    try:
        initial_data = await reader.read(1024)
        if not initial_data:
            writer.close()
            await writer.wait_closed()
            return
        parts = initial_data.decode().split()
        if len(parts) < 2:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        path = parts[1]
        segments = [seg for seg in path.split('/') if seg]
        if not segments:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        user_id = segments[0]
        tunnel_info = await get_tunnel(user_id)
        if tunnel_info is None:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        tunnel_reader, tunnel_writer, event = tunnel_info # 获取 event 对象
        # 将 HTTP 请求初始数据发送给隧道连接
        tunnel_writer.write(initial_data)
        await tunnel_writer.drain()
        # 开启双向数据转发
        task1 = asyncio.create_task(async_pipe(reader, tunnel_writer))
        task2 = asyncio.create_task(async_pipe(tunnel_reader, writer))
        await asyncio.gather(task1, task2)

    except Exception as e:
        print("处理 HTTP 请求错误:", addr, e)
    finally:
        #  通知隧道连接关闭
        if tunnel_info: # 确保 tunnel_info 存在
            _, _, event = tunnel_info
            event.set() # 设置 Event 对象，通知隧道关闭
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def control_server():
    server = await asyncio.start_server(handle_tunnel_connection, host="", port=59854)
    print("控制服务器监听 59854 端口")
    async with server:
        await server.serve_forever()

async def http_server():
    server = await asyncio.start_server(handle_http_connection, host="", port=57487)
    print("数据/HTTP 服务器监听 57487 端口")
    async with server:
        await server.serve_forever()

async def main():
    await asyncio.gather(
        control_server(),
        http_server(),
    )

if __name__ == "__main__":
    asyncio.run(main())
