目录
=================

* [简介](#简介)
* [测试流程](#测试流程)
* [测试须知](#测试须知)
    * [环境](#环境)
        * [测试机](#测试机)
        * [部署机](#部署机)
    * [安装区块链的主机的条件](#安装区块链的主机的条件)
        * [Docker 安装与配置](#Docker-安装与配置)
        * [sshd 服务的安装与配置](#sshd-服务的安装与配置)
        * [/data 文件夹的创建](data-文件夹的创建)
* [文件结构](#文件结构)
* [使用步骤](#使用步骤)
    * [v1.3 版本使用步骤](#v13-版本使用步骤)
    * [v2.0 版本使用步骤](#v20-版本使用步骤)


## 简介

fisco-bcos-autobench 是一个用来一键【部署区块链、进行压力测试、收集实验数据】的工具，使用 python 编写，它减少了过程中的重复劳动，可节省大量时间和精力，利用简单的配置即可一键获取若干条数据，不易出错，非常适合实验数据的收集。

## 测试流程

本工具集成 caliper v0.3.2 ，工具内部的测试步骤为：
1. `build_chain.sh` 生成区块链配置。
2. 根据本工具提供的选项更改某些配置。
3. 生成 基准测试配置文件 和 网络配置文件 供 caliper 使用。
4. 将区块链配置复制到所有远程主机。
5. 调用 caliper 进行测试：远程启动 Docker 容器构建起区块链，本地发起请求作为工作负载进行测试，完成之后生成报告，最后远程停止区块链。
6. 整理报告生成测试结果。

> 对 BCOS 部署、测试 还不熟悉？看一看 [参考资料](#参考资料) 或 [官方文档](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/)

## 测试须知

我们把测试用的主机称为**测试机**，部署区块链的主机称为**部署机**。一般情况下，需要两台及以上的服务器进行测试，也可使用虚拟机进行模拟实验。

### 环境

"工欲善其事，必先利其器"，使用本工具的前提是配置好相应的环境。

本工具支持测试在多主机上部署区块链。一般来说，需要一台主机满足测试机的条件，一台或多台主机满足部署机的条件。

#### 测试机

1. 克隆本仓库：`git clone https://github.com/dfface/fisco-bcos-autobench.git`
2. 安装 node 依赖： `npm install` （node 版本请保持在 v8.X.X，可使用 [nvm](https://github.com/nvm-sh/nvm) 管理）
3. 安装 python 依赖： `pip install -r requirements.txt` （python 版本应为 v3.X.X）

#### 部署机

所有主机应尽可能保持一致，特别是 `root` 用户的密码是一致的。

1. Docker 安装与配置

首先需要安装 Docker 并开启Docker Daemon服务，Docker 安装看官网教程，比较简单： https://docs.docker.com/engine/install/

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

2. sshd 服务的安装与配置

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

3. 一些用到的 Linux 工具: （v3.0 暂不加入）

3.1. 磁盘信息工具

一般磁盘模式为 `normal` ，可安装 `apt install smartmontools` 查看信息，如:

```bash
smartctl --all /dev/sda | grep 'User Capacity' | awk -F: '{print $2}'
        21,474,836,480 bytes [21.4 GB]
```

但是如果是磁盘阵列──`raid`模式，则需要安装 `megacli`，以 `ubuntu` 系统为例：

```bash
echo deb http://hwraid.le-vert.net/ubuntu precise main >> /etc/apt/sources.list
wget -O - http://hwraid.le-vert.net/debian/hwraid.le-vert.net.gpg.key | sudo apt-key add -
apt-get update
apt-get install megacli megactl megaraid-status
# 查看驱动器信息
megacli -LDInfo -Lall -aALL 

Adapter 0 -- Virtual Drive Information:
Virtual Drive: 0 (Target Id: 0)
Name                :
RAID Level          : Primary-5, Secondary-0, RAID Level Qualifier-3
Size                : 278.875 GB
Sector Size         : 512
Parity Size         : 139.437 GB

```

> 参考了 [ubuntu安装megacli](https://blog.csdn.net/qq_40907977/article/details/107468520) 以及 [linux 下查看硬盘型号、大小等信息（含Raid）
](https://blog.csdn.net/harbor1981/article/details/42772377) 。
>

#### /data 文件夹的创建

每台区块链主机上必须要有一个可读写的 `/data` 文件夹。

``` bash
sudo mkdir /data
sudo chmod 777 /data
```

！！！到此为止，我这里已经有一台配置好的 Ubuntu 18.04 Server系统虚拟机可用（使用 vmware ），下载后可直接用，[地址](https://bhpan.buaa.edu.cn:443/link/D5D02F07710917781E8B9578348379C3) 有效期限：2025-11-30 23:59。
切记在区块链主机准备好之后，先用测试用主机`ssh`连接这些主机（为了保存`fingerprint`）。
虚拟机可复制，但要注意复制后虚拟机的 `IP` 配置。

## 基准测试

利用
[](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/manual/transaction_parallel.html)

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
├── autobench.log  # 本工具的日志
├── benchmark
│   ├── config.yaml  # 基准测试配置文件
│   ├── get.js
│   └── set.js
├── caliper_history  # caliper 测试的历史日志和报告
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

P.S. 区块链性能测试结果 `data.csv` 文件应不包括本基准测试的相关数据，如 `worker_num` ，为了详尽加上了所有信息，对收集的数据建议进行二次处理。

### v2.0 版本使用步骤

v1.x 版本采用面向过程的方式编程，而v2.0 采用面向对象的方式编程。

#### 使用样例

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

#### 默认值

| 参数 | 类型 | 默认值 |
| :---: | :---: | :---: |
|node_bin_path|str| 无，必须添加，可使用 `which npm` 命令截取，如 "/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/"|
|host_addr|list| 无，必须添加，可查看要部署区块链的主机的 IP|
|root_password| str |（方便起见，部署区块链的所有主机应具有相同的root密码）'123456'|
|consensus_type| str |（共识类型，可选 pbft、raft、rpbft）'pbft'|
|storage_type| str |（存储类型）'rocksdb'|
|tx_num| int |（测试事务总量）10000|
|tx_speed| int |（测试事务发送速率）1000|
|block_tx_num| int |（区块打包交易数）1000|
|epoch_sealer_num| int |（仅对 rpbft 有效）4|
|consensus_timeout| int |（共识超时时间，最低3s）3|
|epoch_block_num| int |（仅对 rpbft 有效）1000|
|node_num| int |（节点总数）4|
|sealer_num| int |（共识节点数）4|
|worker_num| int |（测试主机工作进程数）1|
|node_outgoing_bandwidth| int |（节点带宽限制，0表示不限制，1表示限制1M/s）0|
|group_flag| int |1|
|agency_flag| str |'dfface'|
|network_config_file_path| str |'./network/fisco-bcos.json'|
|benchmark_config_file_path| str |'./benchmark/config.yaml'|
|ipconfig_file_path| str |'./network/ipconfig'|
|p2p_start_port| int |30300|
|channel_start_port| int |20200|
|jsonrpc_start_port| int |8545|
|contract_type| str |'solidity'|
|state_type| str |'storage'|
|contract_path| str |'./smart_contracts/HelloWorld.sol'|
|log_level| enum |logging.ERROR|

### v2.1 版本使用步骤

v2.1 将每次测试结果获取方式进行了更改，这之前是从命令行中获取，这之后从 caliper 的日志中获取。

本版本是小更新，使用方法同 v2.0 。

## 参考资料

* [性能压测工具Caliper在FISCO BCOS平台中的实践](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/articles/4_tools/46_stresstest/caliper_stress_test_practice.html)
* [Caliper压力测试指南](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/manual/caliper.html)
* [配置文件和配置项](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/manual/configuration.html)
* [并行合约](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/manual/transaction_parallel.html)
* [智能合约开发](https://fisco-bcos-documentation.readthedocs.io/zh_CN/latest/docs/manual/smart_contract.html)