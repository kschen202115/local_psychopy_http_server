# 这是一个简单psychopy的线上实验服务
## 简介
虽然psychopy自带本地线上实验的浏览，但是他无法实现外网访问。所以如果要让他人访问必须借助各类线上实验平台
本项目就是为了解决这个问题
## 使用方法
在本地预览过线上实验后，将http_server.py放在实验的根目录
并执行 python http_server.py 会在当前路径启动一个简单文件服务
然后再执行python tunnel_client.py
会随机生成一个用户id和访问地址
## 使用ui快速开始（不推荐）
存在无法注销用户id的问题，导致出现同一id在手动断开连接后可能会注册失败的问题
### 通用 
需要安装flask
将uii.py放在实验根目录，然后执行 python uii.py
即可打开ui界面
### windows
下载打包好的exe程序，并放在实验根目录，双击运行
## 写在最后
本项目是提供了国内垃圾服务器，共享带宽200M，cpu很差请勿压测
出于个人原因本项目只提供简单的服务
无法将远程文件保存到本地，只能手动通过通讯工具发送结果
如果需要在线保存文件可以访问网站
www.psyexp.tech
