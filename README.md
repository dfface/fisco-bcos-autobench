![fisco-bcos-autobench](https://cdn.jsdelivr.net/gh/dfface/img0@master/1/Snipaste_2021-01-06_16-30-29.png)

English Version | [中文版本](https://github.com/dfface/fisco-bcos-autobench/blob/master/README_zh.md)

## Introduction

fisco-bcos-autobench is a tool used to deploy blockchain, perform stress testing, and collect experimental data with one click. 
It is written in python. 
It reduces duplication of labor in the process, can save a lot of time and energy, and is easy to use.
It can get several pieces of data with one click, which is not easy to make mistakes and is very suitable for the collection of experimental data.

This document covers the following:

* [Introduction](#introduction)
* [Test Process](#test-process)
* [Test Instructions](#test-instructions)
    * [Environment](#environment)
        * [Testing Machine](#testing-machine)
        * [Deploying Machine](#deploying-machine)
            * [Docker Installation and Configuration](#docker-installation-and-configuration)
            * [sshd Service Installation and Configuration](#sshd-service-installation-and-configuration)
* [Benchmark Test](#benchmark-test)
* [File Structure](#file-structure)
* [Usage](#usage)
* [Default Values](#default-values)
* [Related Information](#related-information)

## Test Process

Blockchain platform based on FISCO BCOS can be tested. 
This tool relies on Caliper v0.3.2, the test steps inside the tool are:
1. `build_chain.sh` generates the blockchain configuration.
2. Change some configurations according to the options provided by this tool.
3. Generate benchmark test configuration files and network configuration files for caliper to use.
4. Copy the blockchain configuration file to the `/data` directory of all remote hosts.
5. Call caliper to test: remotely start the Docker container to build a blockchain, and locally initiate a request as a workload for testing
[You can view the path of the deployment machine `/data` during testing, and save the **real-time data and log information** of the blockchain! ], generate a report after completion, and finally stop the blockchain remotely.
6. Organize reports and generate test results.

> Not familiar with FISCO BCOS deployment and testing? Take a look at [Related Information](#related-information) or [FISCO BCOS Official Document](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/)

## Test Instructions

We call the host used for testing as the **testing machine**, and the host for deploying the blockchain as the **deploying machine**. In general, two or more servers are required for testing, and virtual machines can also be used for simulation experiments.

### Environment

"Workers must first sharpen their tools if they want to do their jobs well". The premise of using this tool is to configure the corresponding environment.

This tool supports testing the deployment of blockchain on multiple hosts. Generally speaking, one host is required to meet the conditions of the test machine, and one or more hosts meet the conditions of the deployment machine.

#### Testing Machine

1. Clone this repository: `git clone https://github.com/dfface/fisco-bcos-autobench.git`
2. Install node dependencies: `npm install` (Please keep the node version stable, such as v8.17.0, which can be managed by [nvm](https://github.com/nvm-sh/nvm))
3. Install python dependencies: `pip install -r requirements.txt` (Python version should be v3.7.X)

#### Deploying Machine

All hosts should be consistent as much as possible, especially the password of the `root` user is consistent (unify it for the convenience of the experiment).

##### Docker Installation and Configuration

First, you need to install Docker and enable the Docker Daemon service. For Docker installation, see the official website tutorial, which is relatively simple: https://docs.docker.com/engine/install/

Then you need to start the Docker Daemon service:

`sudo service docker stop` first stop the service (if it is `snap` installation, the command is `sudo snap stop docker`).

Create the `/etc/docker/daemon.json` file:

``` json
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2375"]
}
```

> "Unix:///var/run/docker.sock": UNIX socket, the local client will connect to Docker Daemon through this; tcp://0.0.0.0:2375, TCP socket, which means any The remote client connects to Docker Daemon through port 2375.

Use `sudo systemctl edit docker` to create or modify `/etc/systemd/system/docker.service.d/override.conf`

``` ini
##Add this to the file for the docker daemon to use different ExecStart parameters (more things can be added here)
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
```

Restart the service:

``` bash
sudo systemctl daemon-reload
sudo systemctl restart docker.service
```

At this point, you can access the local Docker service through a remote connection on another machine, for example:

![image-20200928165131712](https://cdn.jsdelivr.net/gh/dfface/img0@master/0/image-20200928165131712-stEkHT.png)

##### sshd Service Installation and Configuration

Since the tool uses the ssh command, you need to install and configure the root user to log in.

``` bash
# Change the root user password, for example to 123456
sudo passwd root
# Install sshd service
sudo apt-get install -y openssh-server
# Modify the configuration Change the line "#PermitRootLogin ..." to "PermitRootLogin yes"
vi /etc/ssh/sshd-config
# Restart sshd service
service sshd restart
# After this, you can connect to this machine through ssh on other machines. Remember to ssh to connect to all blockchain hosts before using the script
```

## Benchmark Test

This tool contains two benchmark tests adapted to FISCO BCOS in Caliper V0.3.2. The updated content can be viewed at [hyperledger/caliper-benchmarks](https://github.com/hyperledger/caliper-benchmarks/tree/master/benchmarks/samples/fisco-bcos).

By default, `transfer` is used instead of `helloworld`.

## File Structure

Structure before the tool is used:

``` txt
├── README.md
├── autobench.py ​​# Automation tool
├── benchmarks # Benchmark test folder, including helloworld and transfer
│ ├── helloworld
│ └── transfer
├── network # network configuration
│ ├── build_chain.sh # Development and deployment tools
│ └── fisco-bcos.json # Caliper network configuration
├── package-lock.json
├── package.json # node dependency
├── requirements.txt # python dependencies
├── smart_contracts # smart contract folder
 ├── helloworld
 └── transfer
```

After each test, some files will be generated to verify the test situation, for example:

``` txt
.
├── autobench.py
├── autobench.log # This tool's log
├── benchmark
│ ├── helloworld
│ └── transfer
│ └── solidity
│ └── config.yaml # Benchmark configuration file
├── caliper_history # caliper test history log and report
│ ├── log # The history log is saved, the internal files of the folder are omitted
│ └── report # The historical report is saved, the internal files in the folder are omitted
├── network
│ ├── build_chain.sh
│ ├── fisco-bcos.json # Network configuration file
│ ├── ipconfig # Configuration file for nodes generation
│ └── nodes # Blockchain nodes folder
├── smart_contracts
│ ├── helloworld
│ └── transfer
│ └── ParallelOk.address # Contract address
├── caliper.log # The log of the current round of testing
├── report.html # The report of the current round of testing
├── data.csv # Cumulative experimental data
├── package-lock.json
├── package.json
└── requirements.txt
```

## Usage

First configure the host according to the preconditions.

Then create a new `test.py` file, a simple example is as follows:

```python
from autobench import AutoBench

autobench = AutoBench("/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/",
                      ["192.168.177.153", "192.168.177.154"]) # gives the environment variables of node and the addresses of the two deployment machines
# Some parameters can be changed in between
# Finally call test_once() to test
autobench.test_once()
```

P.S. Blockchain performance test results The `data.csv` file should not include the relevant data of this benchmark test, such as `worker_num`. In order to add all the information in detail, it is recommended to perform secondary processing on the collected data.

The output is similar:

```bash
auto benchmark 2 host(s) 5 nodes: 24%|██▍ | 32.0/132 [00:14<02:27, 1.48s/B]
```

## Default Values

| Parameters | Type | Meaning | Default Value |
| :---: | :---: | :---: | :---: |
|node_bin_path|str| node environment variable, which can be intercepted with `which npm` command, such as "/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/"| None, must be added |
|host_addr|list| Deployment machine IP list| None, must be added |
|root_password| str | (For convenience, all hosts where the blockchain is deployed should have the same root password) | None, must be added |
|benchmark| str |Select benchmark test, optional'transfer','helloworld'| `'transfer'` |
|consensus_type| str | Consensus algorithm type, optional'pbft','raft','rpbft' | `'pbft'`|
|storage_type| str |Storage type, currently only supports'rocksdb' |`'rocksdb'`|
|tx_num| int | The total number of transactions set by the test | `10000`|
|tx_speed| int | Test the set transaction sending rate |`5000`|
|block_tx_num| int | The number of block packaged transactions, the maximum number of transactions that can be packaged in a block | `1000` |
|epoch_sealer_num| int | (Only valid for rpbft) The number of consensus nodes participating in each round of consensus |`4`|
|consensus_timeout| int |In the PBFT consensus process, the block execution timeout time, minimum 3s |`3`|
|epoch_block_num| int | (Only valid for rpbft) Number of blocks produced in one consensus cycle | `1000`|
|node_num| int |Total number of nodes (number of observation nodes + number of consensus nodes)|`4`|
|sealer_num| int |Number of consensus nodes|`4`|
|worker_num| int |The number of worker processes of the test host|`1`, it is recommended to increase according to the number of CPU cores|
|node_outgoing_bandwidth| int |Node outgoing bandwidth limit, 0 means no limit, 1 means limit 1M/s|`0`|
|group_flag| int |group flag|`1`|
|agency_flag| str |Agency flag|`'dfface'`|
|hardware_flag| str |Hardware flag|`'home'`|
|network_config_file_path| str | Caliper network configuration file location |`'./network/fisco-bcos.json'`|
|benchmark_config_file_path| str | Caliper benchmark configuration file location |`'./benchmark/config.yaml'`|
|ipconfig_file_path| str | Development and deployment tool configuration file location |`'./network/ipconfig'`|
|p2p_start_port| int |p2p start port number, it is not recommended to change |`30300`|
|channel_start_port| int |channel start port number, it is not recommended to change |`20200`|
|jsonrpc_start_port| int | jsonrpc starting port number, it is not recommended to change | `8545`|
|docker_port| int | docker remote access port number, if configured according to the preconditions, this item does not need to be changed | `2375`|
|contract_type| str |Smart contract type, transfer test supports'precompiled' and'solidity', helloworld only supports'solidity'|`'solidity'`|
|state_type| str |state type|`'storage'`|
|log_level| str | The log level of this tool, support warn, info, error, debug | `'info'` |
|node_log_level| str | The level of the local log of the blockchain node, which supports trace, debug, info| `'info'` |
| tx_per_batch | int | transfer benchmark test, you can set how many transactions are processed in batches each time|`10`|
|nohup|bool|Whether to display the dynamic output progress bar, when using the linux `nohup` command (`True`), its display can be suppressed (ie not displayed), the default display |`False`|
|data_file_name|str|Data collection file name without suffix, only `.csv` file is supported|`'data'`|
|log_file_name|str|The log file name of this tool without suffix|`'autobench'`|
|docker_monitor|bool|Whether to enable docker monitoring, it is enabled by default |`True`|
|blockchain_with_docker|str|FICSO BCOS-based blockchain container on dockerhub|`'fiscoorg/fiscobcos:v2.6.0'`|
------

## Related Information

* [Practice of Caliper, a performance stress measurement tool in the FISCO BCOS platform](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/articles/4_tools/46_stresstest/caliper_stress_test_practice.html)
* [Caliper Stress Test Guide](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/caliper.html)
* [Configuration files and configuration items](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/configuration.html)
* [Parallel Contract](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/transaction_parallel.html)
* [Smart Contract Development](https://fisco-bcos-documentation.readthedocs.io/zh_CN/v2.6.0/docs/manual/smart_contract.html)
