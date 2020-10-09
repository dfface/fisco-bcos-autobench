## 简介

fisco-bcos-autobench 是一个可以用来一键【部署区块链、进行压力测试、收集实验数据】的工具，使用 python 编写，它减少了这些过程中的重复劳动节省了大量时间，利用简单的配置即可一键获取若干条数据，非常适合实验数据收集。

## 前置条件

本工具推荐使用一台主机用于测试，若干台主机用于部署区块链。也可以在测试的主机上安装区块链，如果能装得上的话。（如果没那么多主机（服务器）可用，可结合使用 VMware Workstation/Fusion 虚拟机）。

### 安装Caliper的主机的条件

测试机首先也需要安装 Docker ，Docker 安装看官网教程，比较简单：https://docs.docker.com/engine/install/，此外，如果需要在此主机上安装区块链就需要同时满足《安装区块链的主机的条件》。

首先需要按以下步骤操作：（需 nvm、npm、git ）：

``` bash
# 安装 nvm 
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.36.0/install.sh | bash
# 使用 node 8
source ~/.$(basename $SHELL)rc
nvm install 8
nvm use 8
node --version # 确认为 8，无论执行什么命令先检查 node 版本
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.36.0/install.sh | bash
# 克隆本仓库
git clone https://github.com/dfface/fisco-bcos-autobench.git
# 安装 node 依赖
npm install
```

还需要安装python相关依赖（依赖在 requirements.txt 中，python 建议版本 >= 3.7）：

``` bash
pip install -r requirements.txt
```

还需要安装系统工具 `sshpass` ，它因系统而异，推荐使用 Linux、macOS（macOS只能作为测试机，不能安装区块链），可参考 [installing SSHPASS](https://gist.github.com/arunoda/7790979)。

``` bash
# 如果是 ubuntu
sudo apt install -y sshpass
# 如果是 macOS，前提是安装了 homebrew
brew tap esolitos/ipa
brew install sshpass
```

**！！！**到此为止，我这里已经有一台配置好的 Ubuntu 18.04 桌面系统虚拟机可用（使用 vmware ），下载后可直接用。

在后面 《安装区块链的主机的条件》 完全具备之后，需要先使用 `ssh`  命令连接上**所有其他主机**，以提前保存 `fingerprint`（如果在测试阶段又新增了主机，**切记**要先手动用`ssh`连接，不然会出错）：

![image-20201007003801316](https://cdn.jsdelivr.net/gh/dfface/img0@master/0/image-20201007003801316-AndA0W-4uqKjj.png)

### 安装区块链的主机的条件

所有主机应尽可能保持一致，使用虚拟机的好处是可以在配置完一台之后直接复制，但需要注意复制的虚拟机需要先重启一下以更新网络等配置。此主机默认使用 Ubuntu 18.04 Server 版。

#### Docker 安装与配置

首先需要安装 Docker 并开启Docker Daemon服务，Docker 安装看官网教程，比较简单： https://docs.docker.com/engine/install/。

然后需要开启 Docker Daemon 服务：

`sudo service docker stop` 先停服务（如果是 `snap` 安装则命令为 `sudo snap stop docker`）。

创建`/etc/docker/daemon.json`文件：

``` json
{
  "hosts" : ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2375"]
}
```

> “unix:///var/run/docker.sock”：UNIX套接字，本地客户端将通过这个来连接Docker Daemon； tcp://0.0.0.0:2375，TCP套接字，表示允许任何远程客户端通过2375端口连接Docker Daemon.

使用`sudo systemctl edit docker`新建或修改`/etc/systemd/system/docker.service.d/override.conf`

``` ini
##Add this to the file for the docker daemon to use different ExecStart parameters (more things can be added here)
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
```

重启服务：

``` bash
sudo systemctl daemon-reload
sudo systemctl restart docker.service
```

此时能够在另一台机器上通过远程连接访问本机的Docker服务，例如：

![image-20200928165131712](https://cdn.jsdelivr.net/gh/dfface/img0@master/0/image-20200928165131712-stEkHT.png)

#### sshd 服务的安装与配置

由于工具用到了 ssh 命令，因此需要安装并配置root用户可登录。

``` bash
# 更改 root 用户密码，例如改为 123456
sudo passwd root
# 安装 sshd 服务
sudo apt-get install -y openssh-server
# 修改配置 将 "#PermitRootLogin ..." 一行改为 "PermitRootLogin yes"
vi /etc/ssh/sshd-config
# 重启 sshd 服务
service sshd restart
# 这之后在别的机器上可以通过 ssh 连接本机，使用脚本之前切记先 ssh 连接所有区块链主机
```

#### /data 文件夹的创建

每台区块链主机上必须要有一个可读写的 `/data` 文件夹。

``` bash
sudo mkdir /data
sudo chmod 777 /data
```

**！！！**到此为止，我这里已经有一台配置好的 Ubuntu 18.04 Server系统虚拟机可用（使用 vmware ），下载后可直接用。切记在区块链主机准备好之后，先用测试用主机`ssh`连接这些主机（为了保存`fingerprint`）。

## 文件结构

工具使用之前的结构：

``` txt
.
├── autobench.py  # 自动化工具
├── benchmark  # 基准测试文件夹
│   ├── get.js
│   └── set.js
├── network  # 网络配置文件夹
│   └── build_chain.sh
├── smart_contracts  # 智能合约文件夹
│   └── HelloWorld.sol
├── package-lock.json
├── package.json  # node 依赖
└── requirements.txt  # python 依赖
```

每次测试之后，会生成一些文件，可供检验此次测试情况：

``` txt
.
├── autobench.py
├── benchmark
│   ├── config.yaml  # 基准测试配置文件
│   ├── get.js
│   └── set.js
├── caliper_history  # caliper 历史日志和报告
│   ├── log  # 保存了历史日志，文件夹内部文件略
│   └── report  # 保存了历史报告，文件夹内部文件略
├── network
│   ├── build_chain.sh
│   ├── fisco-bcos.json  # 网络配置文件
│   ├── ipconfig  # nodes 生成用配置文件
│   └── nodes  # 区块链 nodes 文件夹
├── smart_contracts  
│   ├── HelloWorld.address  # 合约地址
│   └── HelloWorld.sol
├── caliper.log  # 当前一轮测试的日志
├── report.html  # 当前一轮测试的报告
├── data.csv  # 累计的实验数据
├── package-lock.json
├── package.json
└── requirements.txt
```

## 使用步骤

先按照前置条件配置好主机。可以直接下载配置好的两台虚拟机，一台桌面版专供测试，一台服务器版用于复制成集群安装区块链。

然后用 vmware **开启所有**虚拟机，并在桌面版**测试用虚拟机登录**进入桌面，然后通过命令行`ssh`连接（使用`ssh root@192.168.XXX.XXX` 以保存 `fingerprint`）到所有**区块链用虚拟机**（也需要登录以获取局域网ip地址，使用`ifconfg`命令查看ip）。

以上内容完成之后，就可以进行测试了，**除非**新增了区块链用虚拟机，**否则**无需进行任何其他操作（指的是 `ssh` 保存 `fingerprint`），后面的操作只需要用到本自动化工具。

### v1.3 版本使用步骤

完成前置条件之后，必须先根据系统情况修改【# 1 system settings】，然后可根据实验要求修改其他参数【# 2 test options】（例如 `host_addr` 参数等），之后直接运行即可，适合一次性任务。

``` python
# 1 system settings
node_bin_path = "/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/"  # 'which npm' then you find the bin path
root_password = "123456"  # must be root's password, PermitRootLogin yes (keep consistent with all hosts)
# 2 test options
consensus_type = "pbft"  # (pbft raft rpbft)
storage_type = "rocksdb"  # (rocksdb mysql external scalable)
tx_num = 10000  # the total number of transactions
tx_speed = 1000  # the max speed of sending transactions (tps)
block_tx_num = 1000  # the max number of transactions of a block
epoch_sealer_num = 4  # the working sealers num of each consensus epoch
consensus_timeout = 3  # in seconds, block consensus timeout, at least 3s
epoch_block_num = 1000  # the number of generated blocks each epoch
host_addr = ["192.168.177.153", "192.168.177.154"]  # the host address of each server
node_num = 4  # the total num of nodes (sealer & follower)
sealer_num = 4  # the total num of sealer nodes (consensusers)
# better not to change
worker_num = 1  # specifies the number of worker processes to use for executing the workload (caliper)
node_outgoing_bandwidth = 0  # 0 means no limit
```

修改好参数之后，直接运行此文件即可。

P.S. 区块链性能测试结果 `data.csv` 文件应该不包括本基准测试的相关数据，如 `worker_num` ，但为了详尽加上了，对收集的数据可以进行二次处理。

### v2.0 版本使用步骤

v1.x 版本采用面向过程的方式编程，而v2.0 采用面向对象的方式编程。
在本项目根目录下新建一个文件，如`test.py`，然后创建对象，调用`test_once`方法即可：
```python
from autobench import AutoBench

autobench = AutoBench("/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/",
                      ["192.168.177.153", "192.168.177.154"],
                      node_num=5)
autobench.test_once()
```
输出类似：
```bash
auto benchmark 2 host(s) 5 nodes:  24%|██▍       | 32.0/132 [00:14<02:27, 1.48s/B]
```

