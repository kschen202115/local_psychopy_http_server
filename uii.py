import tkinter as tk
from tkinter import scrolledtext
import multiprocessing
import asyncio
import random
import string
import socket
from flask import Flask, render_template_string, send_from_directory
import os
import queue

# Flask 服务器
app = Flask(__name__)

def get_files():
    return [f for f in os.listdir('./') if os.path.isfile(f)]

@app.route('/<id>/')
def index(id):
    files = get_files()
    file_list = "<br>".join([f'<a href="/{id}/{f}">{f}</a>' for f in files])
    return render_template_string("""
        <h1>文件列表</h1>
        <p>{{ file_list | safe }}</p>
    """, file_list=file_list)

@app.route('/<id>/<path:filename>')
def serve_static(filename, id):
    return send_from_directory('./', filename)

def run_flask(log_queue):
    log_queue.put("启动 HTTP 服务器\n")
    app.run(host='0.0.0.0', port=45678, debug=False)

async def async_pipe(reader, writer):
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        pass
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_tunnel(tunnel_reader, tunnel_writer, local_http_port):
    try:
        local_reader, local_writer = await asyncio.open_connection("127.0.0.1", local_http_port)
        task1 = asyncio.create_task(async_pipe(tunnel_reader, local_writer))
        task2 = asyncio.create_task(async_pipe(local_reader, tunnel_writer))
        await asyncio.gather(task1, task2)
    except Exception as e:
        pass
    finally:
        tunnel_writer.close()
        await tunnel_writer.wait_closed()

exit_event = asyncio.Event()  # 退出信号

async def tunnel_worker(log_queue, server_ip, tunnel_port, user_id, local_http_port):
    while not exit_event.is_set():  # 只有当 exit_event 被设置时，任务才会退出
        try:
            tunnel_reader, tunnel_writer = await asyncio.open_connection(server_ip, tunnel_port)
            tunnel_writer.write(f"TUNNEL {user_id}\n".encode())
            await tunnel_writer.drain()
            log_queue.put("隧道连接已建立\n")
            await handle_tunnel(tunnel_reader, tunnel_writer, local_http_port)
        except Exception as e:
            log_queue.put(f"隧道任务错误: {e}\n")
        await asyncio.sleep(1)

async def main(log_queue, server_ip, tunnel_port, user_id, num, local_http_port):
    global exit_event
    exit_event.clear()  # 重新启动前清空退出标志

    log_queue.put(f"客户端启动，用户 ID: {user_id}\n")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((server_ip, tunnel_port))
        s.send(f"REGISTER {user_id}\n".encode())
        data = s.recv(1024).decode()

        if data == 'SUCCESS':
            log_queue.put("注册成功，启动隧道\n")

            # 存储所有任务
            tasks = [asyncio.create_task(tunnel_worker(log_queue, server_ip, tunnel_port, user_id, local_http_port)) for _ in range(num)]
            
            # 等待所有任务结束
            await asyncio.gather(*tasks)

        else:
            log_queue.put("注册失败\n")
    except Exception as e:
        log_queue.put(f"连接服务器失败: {e}\n")

def run_tunnel(log_queue, server_ip, tunnel_port, user_id, num):
    asyncio.run(main(log_queue, server_ip, tunnel_port, user_id, num, 45678))

def run_tunnel(log_queue, server_ip, tunnel_port, user_id,num):
    asyncio.run(main(log_queue, server_ip, tunnel_port, user_id,num, 45678))

# Tkinter UI
class TunnelUI:
    def __init__(self, root):
        self.root = root
        self.root.title("远程psychopy")

        tk.Label(root, text="用户 ID:").pack()
        self.user_id_entry = tk.Entry(root)
        self.user_id_entry.pack()
        self.user_id_entry.insert(0, ''.join(random.choices(string.ascii_letters + string.digits, k=8)))

        tk.Label(root, text="服务器 IP:").pack()
        self.server_ip_entry = tk.Entry(root)
        self.server_ip_entry.pack()
        self.server_ip_entry.insert(0, "113.206.134.78")

        tk.Label(root, text="隧道端口:").pack()
        self.tunnel_port_entry = tk.Entry(root)
        self.tunnel_port_entry.pack()
        self.tunnel_port_entry.insert(0, "59854")

        tk.Label(root, text="线程数:").pack()
        self.thread_num = tk.Entry(root)
        self.thread_num.pack()
        self.thread_num.insert(0, "5")

        self.log_http = scrolledtext.ScrolledText(root, width=50, height=10)
        self.log_http.pack()
        self.start_http_button = tk.Button(root, text="启动 HTTP 服务器", command=self.start_http)
        self.start_http_button.pack()
        self.stop_http_button = tk.Button(root, text="停止 HTTP 服务器", command=self.stop_http, state=tk.DISABLED)
        self.stop_http_button.pack()

        self.log_tunnel = scrolledtext.ScrolledText(root, width=50, height=10)
        self.log_tunnel.pack()
        self.start_tunnel_button = tk.Button(root, text="启动隧道客户端", command=self.start_tunnel)
        self.start_tunnel_button.pack()
        self.stop_tunnel_button = tk.Button(root, text="停止隧道客户端", command=self.stop_tunnel, state=tk.DISABLED)
        self.stop_tunnel_button.pack()

        self.processes = {}
        self.log_queues = {
            "http": multiprocessing.Queue(),
            "tunnel": multiprocessing.Queue(),
        }
        self.update_logs()

    def start_http(self):
        self.log_http.insert(tk.END, "启动 HTTP 服务器\n")
        p = multiprocessing.Process(target=run_flask, args=(self.log_queues["http"],))
        p.start()
        self.processes['http'] = p
        self.start_http_button.config(state=tk.DISABLED)
        self.stop_http_button.config(state=tk.NORMAL)

    def stop_http(self):
        self.log_http.insert(tk.END, "停止 HTTP 服务器\n")
        if 'http' in self.processes:
            self.processes['http'].terminate()
            del self.processes['http']
        self.start_http_button.config(state=tk.NORMAL)
        self.stop_http_button.config(state=tk.DISABLED)

    def start_tunnel(self):
        user_id = self.user_id_entry.get()
        server_ip = self.server_ip_entry.get()
        tunnel_port = int(self.tunnel_port_entry.get())
        thread_num = int(self.thread_num.get())

        self.log_tunnel.insert(tk.END, f"启动隧道客户端 (ID: {user_id}, IP: {server_ip}, 端口: {tunnel_port})\n访问地址http://{server_ip}/{user_id}\n如果时psychopy则访问访问地址\nhttp://{server_ip}:57487/{user_id}/index.html\n")
        p = multiprocessing.Process(target=run_tunnel, args=(self.log_queues["tunnel"], server_ip, tunnel_port, user_id,thread_num))
        p.start()
        self.processes['tunnel'] = p
        self.start_tunnel_button.config(state=tk.DISABLED)
        self.stop_tunnel_button.config(state=tk.NORMAL)

    def stop_tunnel(self):
        self.log_tunnel.insert(tk.END, "正在停止隧道客户端...\n")

        # 设置全局退出事件，通知所有异步任务退出
        global exit_event
        exit_event.set()

        if 'tunnel' in self.processes:
            self.processes['tunnel'].terminate()  # 强制终止
            self.processes['tunnel'].join()  # 等待进程彻底退出
            del self.processes['tunnel']

        self.start_tunnel_button.config(state=tk.NORMAL)
        self.stop_tunnel_button.config(state=tk.DISABLED)

        self.log_tunnel.delete("1.0", tk.END)  # 清理旧日志
        self.log_tunnel.insert(tk.END, "隧道客户端已完全停止\n")

    def update_logs(self):
        for key, log_queue in self.log_queues.items():
            try:
                while True:
                    log = log_queue.get_nowait()
                    if key == "http":
                        self.log_http.insert(tk.END, log)
                        self.log_http.yview(tk.END)
                    elif key == "tunnel":
                        self.log_tunnel.insert(tk.END, log)
                        self.log_tunnel.yview(tk.END)
            except queue.Empty:
                pass
        self.root.after(100, self.update_logs)  

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = TunnelUI(root)
    root.mainloop()
