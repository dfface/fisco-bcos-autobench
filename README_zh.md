![fisco-bcos-autobench](https://cdn.jsdelivr.net/gh/dfface/img0@master/1/Snipaste_2021-01-06_16-30-29.png)

[English Version](https://github.com/dfface/fisco-bcos-autobench/blob/master/README.md) | 中文版本

## 简介

fisco-bcos-autobench 是一个用来一键部署区块链、进行压力测试、收集实验数据的工具，使用 python 编写，它减少了过程中的重复劳动，可节省大量时间和精力，利用简单的配置即可一键获取若干条数据，不易出错，非常适合实验数据的收集。

本说明文件涵盖以下内容：

* [简介](#简介)
* [测试流程](#测试流程)
* [测试须知](#测试须知)
    * [环境](#环境)
        * [测试机](#测试机)
        * [部署机](#部署机)
            * [Docker 安装与配置](#Docker-安装与配置)
            * [sshd 服务的安装与配置](#sshd-服务的安装与配置)
* [基准测试](#基准测试)
* [文件结构](#文件结构)
* [使用步骤](#使用步骤)
* [使用示例](#使用示例)
* [默认值](#默认值)
* [相关资料](#相关资料)

## 测试流程

本工具可测试基于 FISCO BCOS 的区块链平台，依赖 Caliper v0.3.2 ，工具内部的测试步骤为：
1. `build_chain.sh` 生成区块链配置。
2. 根据本工具提供的选项更改某些配置。
3. 生成 基准测试配置文件 和 网络配置文件 供 caliper 使用。
4. 将区块链配置文件复制到所有远程主机的`/data`目录。
5. 调用 caliper 进行测试：远程启动 Docker 容器构建起区块链，本地发起请求作为工作负载进行测试
【测试时可查看部署机`/data`路径，保存了区块链的**实时数据及日志信息**！】，完成之后生成报告，最后远程停止区块链。
6. 整理报告生成测试结果。

> 对 BCOS 部署、测试 还不熟悉？看一看 [相关资料](#相关资料) 或 [官方文档](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/)

## 测试须知

我们把测试用的主机称为**测试机**，部署区块链的主机称为**部署机**。一般情况下，需要两台及以上的服务器进行测试，也可使用虚拟机进行模拟实验。

### 环境

"工欲善其事，必先利其器"，使用本工具的前提是配置好相应的环境。

本工具支持测试在多主机上部署区块链。一般来说，需要一台主机满足测试机的条件，一台或多台主机满足部署机的条件。

#### 测试机

1. 克隆本仓库：`git clone https://github.com/dfface/fisco-bcos-autobench.git`
2. 安装 node 依赖： `npm install` （node 版本请保持稳定版本如 v8.17.0，可使用 [nvm](https://github.com/nvm-sh/nvm) 管理）
3. 安装 python 依赖： `pip install -r requirements.txt` （Python 版本应为 v3.7.X）

#### 部署机

所有主机应尽可能保持一致，特别是 `root` 用户的密码是一致的（为实验的方便统一一下呗）。

##### Docker 安装与配置

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

##### sshd 服务的安装与配置

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

## 基准测试

本工具包含了 Caliper V0.3.2 中适配 FISCO BCOS 的两个基准测试，更新的内容可查看 [hyperledger/caliper-benchmarks](https://github.com/hyperledger/caliper-benchmarks/tree/master/benchmarks/samples/fisco-bcos)。

默认使用 `transfer` 而不是 `helloworld`。

## 文件结构

工具使用之前的结构：

``` txt
├── README.md
├── autobench.py  # 自动化工具
├── benchmarks  # 基准测试文件夹，包含helloworld、transfer两种
│   ├── helloworld
│   └── transfer
├── network  # 网络配置
│   ├── build_chain.sh  # 开发部署工具
│   └── fisco-bcos.json  # Caliper 网络配置
├── package-lock.json
├── package.json  # node 依赖
├── requirements.txt  # python 依赖
├── smart_contracts  # 智能合约文件夹
    ├── helloworld
    └── transfer
```

每次测试之后，会生成一些文件，可供检验此次测试情况，例如：

``` txt
.
├── autobench.py
├── autobench.log  # 本工具的日志
├── benchmark
│   ├── helloworld
│   └── transfer
│     └── solidity
│      └── config.yaml  # 基准测试配置文件
├── caliper_history  # caliper 测试的历史日志和报告
│   ├── log  # 保存了历史日志，文件夹内部文件略
│   └── report  # 保存了历史报告，文件夹内部文件略
├── network
│   ├── build_chain.sh
│   ├── fisco-bcos.json  # 网络配置文件
│   ├── ipconfig  # nodes 生成用配置文件
│   └── nodes  # 区块链 nodes 文件夹
├── smart_contracts  
│   ├── helloworld
│   └── transfer
│    └── ParallelOk.address  # 合约地址
├── caliper.log  # 当前一轮测试的日志
├── report.html  # 当前一轮测试的报告
├── data.csv  # 累计的实验数据
├── package-lock.json
├── package.json
└── requirements.txt
```

## 使用步骤

先按照前置条件配置好主机。

然后新建一个`test.py`文件，一个简单的示例如下：

```python
from autobench import AutoBench

autobench = AutoBench("/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/",
                      ["192.168.177.153", "192.168.177.154"])  # 给出了node的环境变量、两台部署机的地址
# 这之间可对一些参数进行更改
# 最终调用 test_once() 进行测试即可
autobench.test_once()
```

P.S. 区块链性能测试结果 `data.csv` 文件应不包括本基准测试的相关数据，如 `worker_num` ，为了详尽加上了所有信息，对收集的数据建议进行二次处理。

输出类似：

```bash
auto benchmark 2 host(s) 5 nodes:  24%|██▍       | 32.0/132 [00:14<02:27, 1.48s/B]
```

## 使用示例

```python
from autobench import AutoBench
import time

# 创建测试实例，并配置一些参数
autobench = AutoBench("/home/ubuntu/.nvm/versions/node/v8.17.0/bin/", ['192.168.246.9'], '1qaz2wsx3edc')
autobench.nohup = True  # 如果使用了 Linux nohup 命令（`nohup python3 test.py &`），这里就设置为True，从而不输出进度条
autobench.worker_num = 8  # 设置工作进程数，通常对应CPU物理核心数
autobench.tx_num = 50000  # 发送的事务总量
autobench.tx_speed = 5000  # 发送的事务速率
autobench.blockchain_with_docker = 'fiscoorg/fiscobcos:v2.6.0'  # 设置区块链平台，必须是dockerhub上的基于FISCO BCOS的区块链容器

# 常量
MIN_NODE_NUM = 3
MAX_NODE_NUM = 18
MAX_BLOCK_TX_NUM = 5000
MIN_BLOCK_TX_NUM = 1000  # default
STEP_BLOCK_TX_NUM = 10
MAX_NODE_BANDWIDTH = 0  # no limit
MIN_CONSENSUS_TIMEOUT = 3  
MAX_CONSENSUS_TIMEOUT = 3  # no consensus timeout limit

# 测试 rpbft 算法时的阈值
MIN_RPBFT_EPOCH_BLOCK_NUM = 1000
STEP_RPBFT_EPOCH_BLOCK_NUM = 10
MAX_RPBFT_EPOCH_BLOCK_NUM = 5000

# 最好不要频繁切换共识算法。
def do_pbft_test():
    for i in range(MIN_NODE_NUM, MAX_NODE_NUM + 1):
        autobench.node_num = i
        for j in range(2, i + 1):
            autobench.sealer_num = j
            for a in range(MIN_BLOCK_TX_NUM, MAX_BLOCK_TX_NUM + STEP_BLOCK_TX_NUM, STEP_BLOCK_TX_NUM):
                autobench.block_tx_num = a
                for g in ['solidity', 'precompiled']:
                    autobench.contract_type = g
                    autobench.consensus_type = 'pbft'
                    for b in range(0, MAX_NODE_BANDWIDTH + 1):
                        autobench.node_outgoing_bandwidth = b
                        for c in range(3, MAX_CONSENSUS_TIMEOUT + 1):
                            autobench.consensus_timeout = c
                            autobench.test_once()
                            time.sleep(3)


def do_rpbft_test():
    autobench.contract_type = "rpbft"
    for i in range(MIN_NODE_NUM, MAX_NODE_NUM + 1):
        autobench.node_num = i
        for j in range(2, i + 1):
            autobench.sealer_num = j
            for a in range(MIN_BLOCK_TX_NUM, MAX_BLOCK_TX_NUM + STEP_BLOCK_TX_NUM, STEP_BLOCK_TX_NUM):
                autobench.block_tx_num = a
                for g in ['solidity', 'precompiled']:
                    autobench.contract_type = g
                    for k in range(2, j + 1):
                        autobench.epoch_sealer_num = k
                        for f in range(MIN_RPBFT_EPOCH_BLOCK_NUM,
                                       MAX_RPBFT_EPOCH_BLOCK_NUM + STEP_RPBFT_EPOCH_BLOCK_NUM,
                                       STEP_RPBFT_EPOCH_BLOCK_NUM):
                            autobench.epoch_block_num = f
                            for b in range(0, MAX_NODE_BANDWIDTH + 1):
                                autobench.node_outgoing_bandwidth = b
                                for c in range(3, MAX_CONSENSUS_TIMEOUT + 1):
                                    autobench.consensus_timeout = c
                                    autobench.test_once()
                                    time.sleep(3)


do_pbft_test()
do_rpbft_test()
```

## 默认值

| 参数 | 类型 | 含义 | 默认值 |
| :---: | :---: | :---: | :---: |
|node_bin_path|str| node 环境变量，可使用 `which npm` 命令截取，如 "/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/"| 无，必须添加 |
|host_addr|list| 部署机 IP 列表| 无，必须添加 |
|root_password| str |（方便起见，部署区块链的所有主机应具有相同的root密码）| 无，必须添加 |
|benchmark| str |选择基准测试，可选'transfer'、'helloworld'| `'transfer'` |
|consensus_type| str | 共识算法类型，可选 'pbft'、'raft'、'rpbft' | `'pbft'`|
|storage_type| str |存储类型，目前仅支持'rocksdb' |`'rocksdb'`|
|tx_num| int | 测试设定的事务总量 | `10000`|
|tx_speed| int | 测试设定的事务发送速率 |`5000`|
|block_tx_num| int | 区块打包交易数，一个区块最多能打包的交易数 | `1000` |
|epoch_sealer_num| int |（仅对 rpbft 有效）每轮共识参与的共识节点数 |`4`|
|consensus_timeout| int |PBFT共识过程中，区块执行的超时时间，最低3s |`3`|
|epoch_block_num| int |（仅对 rpbft 有效）一个共识周期出块数目 | `1000`|
|node_num| int |节点总数（观察节点数+共识节点数）|`4`|
|sealer_num| int |共识节点数|`4`|
|worker_num| int |测试主机工作进程数|`1`，建议根据CPU核心数适量增加|
|node_outgoing_bandwidth| int |节点出带宽限制，0表示不限制，1表示限制1M/s|`0`|
|group_flag| int |群组标识|`1`|
|agency_flag| str |机构标识|`'dfface'`|
|hardware_flag| str |硬件标识|`'home'`|
|network_config_file_path| str | Caliper 网络配置文件位置 |`'./network/fisco-bcos.json'`|
|benchmark_config_file_path| str | Caliper 基准测试配置文件位置 |`'./benchmark/config.yaml'`|
|ipconfig_file_path| str | 开发部署工具配置文件位置 |`'./network/ipconfig'`|
|p2p_start_port| int |p2p 起始端口号，不建议更改|`30300`|
|channel_start_port| int |channel 起始端口号，不建议更改 |`20200`|
|jsonrpc_start_port| int | jsonrpc 起始端口号，不建议更改 | `8545`|
|docker_port| int | docker 远程访问端口号，若按照前置条件配置，此项无需更改 | `2375`|
|contract_type| str |智能合约类型，transfer测试支持'precompiled'与'solidity'，helloworld仅支持'solidity'|`'solidity'`|
|state_type| str |state 类型|`'storage'`|
|log_level| str | 本工具日志等级，支持 warn、info、error、debug | `'info'` |
|node_log_level| str | 区块链节点本地日志的等级，支持trace、debug、info| `'info'` |
|tx_per_batch|int|transfer基准测试中可设定每次批量处理多少个交易|`10`|
|nohup|bool|是否显示动态输出进度条，当使用linux的`nohup`命令（`True`）时可抑制其显示（即不显示），默认显示|`False`|
|data_file_name|str|数据收集文件名，不含后缀，仅支持`.csv`文件|`'data'`|
|log_file_name|str|本工具日志文件名，不含后缀|`'autobench'`|
|docker_monitor|bool|是否开启docker监控，默认开启|`True`|
|blockchain_with_docker|str|dockerhub上基于FICSO BCOS的区块链容器|`'fiscoorg/fiscobcos:v2.6.0'`|
------

## 相关资料

* [性能压测工具Caliper在FISCO BCOS平台中的实践](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/articles/4_tools/46_stresstest/caliper_stress_test_practice.html)
* [Caliper压力测试指南](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/caliper.html)
* [配置文件和配置项](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/configuration.html)
* [并行合约](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/transaction_parallel.html)
* [智能合约开发](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/smart_contract.html)