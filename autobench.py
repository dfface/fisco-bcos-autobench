import os
import subprocess
import shutil
import logging
import re
import json
from datetime import datetime
import stat
from tqdm import tqdm
import sys
import csv
import paramiko
import tarfile
from yaml import dump
import hashlib
import pandas as pd
import time

# test steps:
# 0 hardware is ready
# 1 set system settings (only once)
# 2 set test options
# 3 run this script


class SSH(object):
    """
    SSH Client Class.
    """

    def __init__(self, host: str, username: str, password: str, port=22):
        """
        ssh params.
        :param host: host ip address
        :param username: username
        :param password: password
        :param port: default 22
        """
        assert isinstance(port, int)
        assert isinstance(host, str)
        assert isinstance(username, str)
        assert isinstance(password, str)
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client = paramiko.SSHClient()

    def exec_command(self, command: str) -> str:
        """
        execute a command.
        :param command:
        :return: output_string
        """
        assert isinstance(command, str)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
            client.connect(self.host, self.port, self.username, self.password)
            stdin, stdout, stderr = client.exec_command(command)
            out_string = stdout.readlines()  # list
            # print(str(out_string))
            stderr.readlines()
            client.close()
            if client is not None:
                del client, stdin, stdout, stderr
            return out_string
        except paramiko.ssh_exception.SSHException as e:
            sys.stderr.write("ssh error, please check ssh configuration.")
            sys.stderr.write(str(e))

    def copy_dir_from_to(self, local_dir: str, remote_dir: str) -> None:
        """
        example:'./nodes' to '/data' means copy './nodes/*' to '/data/nodes/*'
        :param local_dir:
        :param remote_dir:
        :return: None
        """
        assert isinstance(local_dir, str)
        assert isinstance(remote_dir, str)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
            client.connect(self.host, self.port, self.username, self.password)
            sftp = client.open_sftp()
            exec_path = os.getcwd()
            os.chdir(local_dir)
            os.chdir("../")
            file_dir = os.getcwd()
            try:
                file_name = os.path.basename(local_dir) + ".tar.gz"
                tar = tarfile.open(file_name, "w:gz")
                tar.add(os.path.basename(local_dir))
                tar.close()
            except tarfile.TarError:
                print("tar compress failed.")
                sys.exit(0)
            os.chdir(exec_path)
            remote_file_path = os.path.join(remote_dir, file_name)
            local_file_path = os.path.join(file_dir, file_name)
            sftp.put(local_file_path, remote_file_path)
            self.exec_command("tar -zxvf " + remote_file_path + " -C " + remote_dir)
            self.exec_command("rm -rf " + remote_file_path)
            os.remove(local_file_path)
            client.close()
            if client is not None:
                del client
        except paramiko.ssh_exception.SSHException:
            print("ssh error, please check ssh configuration.")
            sys.exit(0)
        except Exception:
            print("copy dir to remote host failed.")


class AutoBench(object):

    def __init__(self, node_bin_path: str, host_addr: list, root_password: str, benchmark='transfer', consensus_type='pbft',
                 storage_type='rocksdb', tx_num=10000, tx_speed=5000, block_tx_num=1000, epoch_sealer_num=4,
                 consensus_timeout=3, epoch_block_num=1000, node_num=4, sealer_num=4, worker_num=1,
                 node_outgoing_bandwidth=0, group_flag=1, agency_flag='dfface', hardware_flag='home',
                 network_config_file_path='./network/fisco-bcos.json',
                 ipconfig_file_path='./network/ipconfig', p2p_start_port=30300,
                 channel_start_port=20200, jsonrpc_start_port=8545, docker_port=2375,
                 contract_type='solidity', state_type='storage', disk_type='normal',
                 log_level='info', node_log_level='info', tx_per_batch=10, nohup=False, data_file_name='data',
                 log_file_name='autobench', docker_monitor=True, blockchain_with_docker='fiscoorg/fiscobcos:v2.6.0',
                 remote_data_path='/data'):
        """
        initialize an AutoBench instance.
        :param node_bin_path: use command 'which npm' then you find the bin path
        :param host_addr: the host address of each server
        :param root_password: must be root's password, PermitRootLogin yes (keep consistent with all hosts)
        :param benchmark: must be helloworld/transfer
        :param consensus_type: must be pbft/raft/rpbft
        :param storage_type: must be rocksdb TODO: mysql/external/scalable
        :param tx_num: the total number of transactions of this test
        :param tx_speed: the max speed of sending transactions (tps) of this test
        :param block_tx_num: the max number of transactions of a block
        :param epoch_sealer_num: the working sealers num of each consensus epoch (rpbft own)
        :param consensus_timeout: in seconds, block consensus timeout, at least 3s
        :param epoch_block_num: the number of generated blocks each epoch (rpbft own)
        :param node_num: the total num of nodes (sealer & follower)
        :param sealer_num: the total num of sealer nodes (consensusers)
        :param worker_num: specifies the number of worker processes to use for executing the workload (caliper)
        :param node_outgoing_bandwidth: the bandwidth among nodes (0 means no limit, 5 means 5MB/s)
        :param group_flag: name of the group
        :param agency_flag: name of the agency
        :param hardware_flag: prefix of the hardware id(hardware_flag-host_num-md5(host_addr))
        :param network_config_file_path: the path of network config file
        :param ipconfig_file_path: the path of ipconfig file
        :param p2p_start_port: the start port of p2p
        :param channel_start_port: the start port of channel
        :param jsonrpc_start_port: the start port of jsonrpc
        :param docker_port: docker remote port
        :param contract_type: must be solidity/precompiled TODO: helloworld add precompiled
        :param disk_type: must be normal/raid TODO: hardware info collection
        :param tx_per_batch: transfer benchmark use.
        :param state_type: must be storage TODO: mpt
        :param node_log_level: must be trace/debug/info
        :param log_level: must be error/warning/info/debug
        :param nohup: if `nohup` command on Linux will be used
        :param data_file_name: `data.csv` can be replaced by `[data_file_name].csv`
        :param log_file_name: `autobench.log` can be replaced by `[log_file_name].log`
        :param docker_monitor: if docker monitor in caliper will be used
        :param blockchain_with_docker: dockerhub tag of the target blockchain platform
        :param remote_data_path: change remote /data to /xxx/data
        """
        # 1 system settings
        self.node_bin_path = node_bin_path
        self.root_password = root_password
        # 2 test options
        #   2.1 benchmark
        self.host_addr = host_addr
        self.tx_num = tx_num
        self.tx_speed = tx_speed
        self.worker_num = worker_num
        self.benchmark = benchmark
        #   2.2 block
        self.block_tx_num = block_tx_num
        self.epoch_block_num = epoch_block_num
        #   2.3 consensus
        self.consensus_type = consensus_type
        self.consensus_timeout = consensus_timeout
        self.node_num = node_num
        self.sealer_num = sealer_num
        self.epoch_sealer_num = epoch_sealer_num
        #   2.4 storage
        self.storage_type = storage_type
        self.state_type = state_type
        #   2.5 network
        self.node_outgoing_bandwidth = node_outgoing_bandwidth
        #   2.6 smart contract
        self.contract_type = contract_type
        # 3 optional settings(better not to change)
        self.group_flag = group_flag
        self.agency_flag = agency_flag
        self.hardware_flag = hardware_flag
        self.network_config_file_path = network_config_file_path
        self.ipconfig_file_path = ipconfig_file_path
        self.p2p_start_port = p2p_start_port
        self.channel_start_port = channel_start_port
        self.jsonrpc_start_port = jsonrpc_start_port
        self.docker_port = docker_port
        self.disk_type = disk_type
        self.tx_per_batch = tx_per_batch
        self.nohup = nohup
        self.data_file_name = data_file_name
        self.node_log_level = node_log_level
        self.docker_monitor = docker_monitor
        self.blockchain_with_docker = blockchain_with_docker
        self.remote_data_path = remote_data_path
        # 4 predefined variables
        self.node_assigned = []  # balance nodes on hosts (many functions may use)
        self.sealer_assigned = []  # balance sealer nodes on hosts (many functions may use)
        # 5 log settings
        self.logger = logging.getLogger('AutoBench')
        self.logger.setLevel(logging.DEBUG)  # must set this
        log_level_trans = {
            "error": logging.ERROR,
            "warning": logging.WARNING,
            "warn": logging.WARN,
            "info": logging.INFO,
            "critical": logging.CRITICAL,
            "debug": logging.DEBUG
        }
        log_format = logging.Formatter('%(asctime)s - %(name)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        file_handler = logging.FileHandler('./{}.log'.format(log_file_name), 'a', 'utf-8')
        file_handler.setFormatter(log_format)
        file_handler.setLevel(log_level_trans[log_level])
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        console_handler.setLevel(log_level_trans[log_level])
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def clean(self) -> None:
        """
        0. clean up before every test.
        need root & it's passwd, openssh-server, PermitRootLogin yes
        :return: None
        """
        # local
        try:
            shutil.rmtree("./network/nodes")
        except FileNotFoundError:
            self.logger.debug("./network/nodes not found.")
        finally:
            self.logger.debug("./network/nodes cleaned.")
        try:
            os.remove(self.ipconfig_file_path)
        except FileNotFoundError:
            self.logger.debug(self.ipconfig_file_path + " not found.")
        finally:
            self.logger.debug(self.ipconfig_file_path + " cleaned.")
        try:
            os.remove(self.network_config_file_path)
        except FileNotFoundError:
            self.logger.debug(self.network_config_file_path + " not found.")
        finally:
            self.logger.debug(self.network_config_file_path + " cleaned.")
        try:
            os.remove("./caliper.log")
        except FileNotFoundError:
            self.logger.debug("./caliper.log not found.")
        finally:
            self.logger.debug("./caliper.log cleaned.")
        try:
            os.remove("./report.html")
        except FileNotFoundError:
            self.logger.debug("./report.html not found.")
        finally:
            self.logger.debug("./report.html cleaned.")
        try:
            os.remove('./network/nodes.tar.gz')
        except FileNotFoundError:
            self.logger.debug("./network/nodes.tar.gz not found.")
        finally:
            self.logger.debug("./network/nodes.tar.gz cleaned.")
        # remote clean
        for host in self.host_addr:
            ssh = SSH(host, 'root', self.root_password)
            ssh.exec_command('rm -rf {}/nodes'.format(self.remote_data_path))
            self.logger.debug("{}: {}/nodes removed.".format(host, self.remote_data_path))
        self.logger.info("### 0. clean up before every test ###")

    def check_parameters(self) -> None:
        """
        1. check parameters' constraints before every test.
        :return: None
        """
        assert self.benchmark in ['helloworld', 'transfer']
        assert self.contract_type in ['solidity', 'precompiled']
        assert self.disk_type in ['normal', 'raid']
        assert self.node_num >= self.sealer_num
        assert self.node_num >= len(self.host_addr)
        if self.consensus_type == "rpbft":
            assert self.sealer_num >= self.epoch_sealer_num
        assert self.consensus_type in ["pbft", "raft", "rpbft"]
        assert self.storage_type in ["rocksdb", "mysql", "external", "scalable"]
        assert self.tx_num > 0
        assert self.tx_speed > 0
        assert self.block_tx_num > 0
        assert self.epoch_sealer_num > 0
        assert self.consensus_timeout >= 3
        assert self.epoch_block_num > 0
        assert len(self.host_addr) > 0
        assert self.node_num > 0
        assert self.sealer_num > 0
        assert self.worker_num > 0
        assert self.node_outgoing_bandwidth >= 0
        assert self.group_flag == 1
        assert self.node_log_level in ['trace', 'debug', 'info']
        self.logger.info("### 1. check parameters' constraints before every test ###")

    def gen_nodes(self) -> str:
        """
        2. generate nodes folder.
        :return: ipconfig_string
        """
        try:
            shutil.rmtree("network/nodes")
        except FileNotFoundError:
            self.logger.debug("network/nodes not found.")
        finally:
            self.logger.debug("network/nodes cleaned.")
        ipconfig_string = ""  # ipconfig file content
        host_num = len(self.host_addr)
        node_num_avg = int(self.node_num / host_num)
        node_num_remain = self.node_num % host_num
        self.node_assigned = [node_num_avg] * (host_num - node_num_remain) + [node_num_avg + 1] * node_num_remain
        sealer_num_avg = int(self.sealer_num / host_num)
        sealer_num_remain = self.sealer_num % host_num
        self.sealer_assigned = [sealer_num_avg] * (host_num - sealer_num_remain) + [sealer_num_avg + 1] * sealer_num_remain
        self.logger.debug(str(self.sealer_num) + " sealers :" + str(self.sealer_assigned))
        for index, host in enumerate(self.host_addr):
            ipconfig_string += "{}:{} {} {} {},{},{}\n".format(host, self.node_assigned[index], self.agency_flag,
                                                               self.group_flag, self.p2p_start_port,
                                                               self.channel_start_port, self.jsonrpc_start_port)
        self.logger.debug("ipconfig file generated.\n" + ipconfig_string)
        with open(self.ipconfig_file_path, "w") as ipconfig:
            ipconfig.write(ipconfig_string)
        node_gen_command = "bash ./network/build_chain.sh -o ./network/nodes -f {} -d -i -s {} -c {}".format(
            self.ipconfig_file_path, self.storage_type, self.consensus_type)
        node_generated_result = subprocess.getoutput(node_gen_command)
        self.logger.debug(node_generated_result)
        self.logger.debug("nodes folder generated.")
        self.logger.info("### 2. generate nodes folder ###")
        return ipconfig_string

    def ch_group_config(self) -> None:
        """
        3. change group.1.genesis file of each node.
        """
        # list in list
        node_assigned_in_detail = [[] for i in range(len(self.node_assigned))]  # [2,2,3]
        node_index_count = 0
        sealer_index_remain = []
        for index, nodes in enumerate(self.node_assigned):
            for i in range(0, nodes):
                node_assigned_in_detail[index].append(node_index_count)  # naid[0] = [0,1] naid[1] = [2,3] ...
                node_index_count += 1
        self.logger.debug("node_assigned_in_detail: " + str(node_assigned_in_detail))
        for index, sealers in enumerate(self.sealer_assigned):  # [1,1,0]
            for i in range(0, sealers):
                sealer_index_remain.append(node_assigned_in_detail[index][i])  # sir = [0,2]
        self.logger.debug("sealer_index_remain: " + str(sealer_index_remain))
        node0_genesis_path = "./network/nodes/{}/node0/conf/group.{}.genesis".format(self.host_addr[0], self.group_flag)
        with open(node0_genesis_path, "r") as group_config,\
                open(node0_genesis_path + '.bk', "w") as group_config_bk:
            for line in group_config:
                line_to_write = re.sub(r"\s*max_trans_num=1000", "    max_trans_num=" + str(self.block_tx_num), line)
                line_to_write = re.sub(r"\s*epoch_sealer_num=3", "    epoch_sealer_num=" + str(self.epoch_sealer_num),
                                       line_to_write)
                line_to_write = re.sub(r"\s*consensus_timeout=3", "    consensus_timeout=" +
                                       str(self.consensus_timeout), line_to_write)
                line_to_write = re.sub(r"\s*epoch_block_num=1000", "    epoch_block_num=" + str(self.epoch_block_num),
                                       line_to_write)
                sealer_node = re.match(r"\s*node.(\d*)=.*", line_to_write)
                if sealer_node:
                    # change sealers(consensusers) to sealer_num
                    self.logger.debug(str(sealer_node.group(1)))
                    if int(sealer_node.group(1)) not in sealer_index_remain:
                        line_to_write = ""
                self.logger.debug(line_to_write)
                group_config_bk.write(line_to_write)
        os.remove(node0_genesis_path)
        os.rename(node0_genesis_path + '.bk', node0_genesis_path)
        # copy group config to other nodes
        for index, host in enumerate(self.host_addr):
            for i in range(0, self.node_assigned[index]):
                if index == 0 and i == 0:
                    continue
                node_genesis_path = "./network/nodes/{}/node{}/conf/group.{}.genesis".format(host, i, self.group_flag)
                self.logger.debug("copy genesis file to " + node_genesis_path)
                os.remove(node_genesis_path)
                shutil.copy(node0_genesis_path, node_genesis_path)
        self.logger.debug("group config files of each node have changed.")
        self.logger.info("### 3. change group.1.genesis file of each node ###")

    def ch_node_config(self) -> None:
        """
        4. change config.ini file of each node.
        :return: None
        """
        # change node config of each node
        for index, host in enumerate(self.host_addr):
            for i in range(0, self.node_assigned[index]):
                node_ini_path = "network/nodes/{}/node{}/config.ini".format(host, i)
                self.logger.debug("change ini file " + node_ini_path)
                with open(node_ini_path, "r") as node_config, open(node_ini_path + '.bk', "w") as node_config_bk:
                    for line in node_config:
                        line_to_write = re.sub(r"\s*level=info", "    level={}".format(self.node_log_level), line)
                        if self.node_outgoing_bandwidth > 0:
                            line_to_write = re.sub(r"\s*;outgoing_bandwidth_limit=2",
                                                   "    outgoing_bandwidth_limit=" +
                                                   str(self.node_outgoing_bandwidth), line_to_write)
                            node_config_bk.write(line_to_write)
                        else:
                            node_config_bk.write(line_to_write)
                os.remove(node_ini_path)
                os.rename(node_ini_path + ".bk", node_ini_path)
        self.logger.debug("node config file generated.")
        self.logger.info("### 4. change config.ini file of each node ###")

    def gen_docker_scripts(self) -> tuple:
        """
        5. generate start & stop scripts.
        :return: start_all_string, stop_all_string
        """
        start_all_string = ""
        stop_all_string = ""
        for index, host in enumerate(self.host_addr):
            for i in range(0, self.node_assigned[index]):
                start_all_string += "docker -H {host}:{docker_port} run -d --rm --name node{i} " \
                                    "-v {remote_data_path}/nodes/{host}/node{i}/:/data -p {p2p_port}:{p2p_port} " \
                                    "-p {channel_port}:{channel_port} -p {jsonrpc_port}:{jsonrpc_port} " \
                                    "-w=/data {blockchain_with_docker} -c config.ini 1> /dev/null && echo " \
                                    "\"\033[32mremote {host} container node{i} started\033[0m\"\n"\
                    .format(host=host, i=i, p2p_port=self.p2p_start_port + i, channel_port=self.channel_start_port + i,
                            jsonrpc_port=self.jsonrpc_start_port + i, docker_port=self.docker_port,
                            blockchain_with_docker=self.blockchain_with_docker, remote_data_path=self.remote_data_path)
                stop_all_string += "docker -H {host}:{docker_port} stop $(docker -H {host} ps -a | grep node{i} | " \
                                   "cut -d \" \" -f 1) 1> /dev/null && echo \"\033[32mremote {host} container " \
                                   "node{i} stopped\033[0m\"\n".format(host=host, i=i, docker_port=self.docker_port)
            # bug fix: delete all containers
            # stop_all_string += "docker -H {host}:{docker_port} stop $(docker -H {host}:{docker_port} ps -q)\n"\
                # .format(host=host, docker_port=self.docker_port)
            # stop_all_string += "docker -H {host}:{docker_port} rm $(docker -H {host}:{docker_port} ps -aq)\n"\
            #     .format(host=host, docker_port=self.docker_port)
        with open("./network/nodes/start_all.sh", "w") as start_all:
            start_all.write(start_all_string)
        with open("./network/nodes/stop_all.sh", "w") as stop_all:
            stop_all.write(stop_all_string)
        os.chmod("./network/nodes/start_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
        os.chmod("./network/nodes/stop_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
        self.logger.debug("start_all.sh & stop_all.sh file generated.")
        self.logger.info("### 5. generate start & stop scripts ###")
        return start_all_string, stop_all_string

    def copy_nodes_to_all_host(self) -> None:
        """
        6. copy nodes to all hosts: need openssh-server, root login, /data full privileges
         (include cleaning)
        :return: None
        """
        for host in self.host_addr:
            ssh = SSH(host, 'root', self.root_password)
            ssh.exec_command('mkdir {}'.format(self.remote_data_path))
            ssh.copy_dir_from_to('network/nodes', self.remote_data_path)
            self.logger.debug("copy to {} {}/nodes".format(host, self.remote_data_path))
        self.logger.debug("copy nodes to all hosts finished.")
        self.logger.info("### 6. copy nodes to all hosts ###")

    def gen_network_config(self) -> None:
        """
        7. generate network config file.
        :return: None
        """
        nodes_json = []
        for index, host in enumerate(self.host_addr):
            for i in range(0, self.sealer_assigned[index]):
                node_json = {"ip": host, "rpcPort": str(self.jsonrpc_start_port + i),
                             "channelPort": str(self.channel_start_port + i)}
                nodes_json.append(node_json)
        self.logger.debug("sealer_nodes_json: " + str(nodes_json))
        network_config_json = {
            "caliper": {
                "blockchain": "fisco-bcos",
                "command": {
                    "start": "network/nodes/start_all.sh; sleep 5s",
                    "end": "network/nodes/stop_all.sh"
                }
            },
            "fisco-bcos": {
                "config": {
                    "privateKey": "bcec428d5205abe0f0cc8a734083908d9eb8563e31f943d760786edf42ad67dd",
                    "account": "0x64fa644d2a694681bd6addd6c5e36cccd8dcdde3"
                },
                "network": {
                    "nodes": nodes_json,
                    "authentication": {
                        "key": "./network/nodes/{}/sdk/node.key".format(self.host_addr[0]),
                        "cert": "./network/nodes/{}/sdk/node.crt".format(self.host_addr[0]),
                        "ca": "./network/nodes/{}/sdk/ca.crt".format(self.host_addr[0])
                    },
                    "groupID": self.group_flag,
                    "timeout": 100000
                },
                "smartContracts": [
                    {
                        "id": "helloworld",
                        "path": "smart_contracts/helloworld/HelloWorld.sol",
                        "language": "solidity",
                        "version": "v0"
                    },
                    {
                        "id": "parallelok",
                        "path": "smart_contracts/transfer/ParallelOk.sol",
                        "language": "solidity",
                        "version": "v0"
                    },
                    {
                        "id": "dagtransfer",
                        "address": "0x0000000000000000000000000000000000005002",
                        "language": "precompiled",
                        "version": "v0"
                    }
                ]
            },
            "info": {
                "Version": "1.0.0",
                "Size": "{} Nodes".format(self.node_num),
                "Distribution": "{} Host(s)".format(len(self.host_addr))
            }
        }
        with open(self.network_config_file_path, "w") as network_config:
            network_config.write(json.dumps(network_config_json))
        self.logger.debug("network config file generated.")
        self.logger.info("### 7. generate network config file ###")

    def gen_benchmark_config(self) -> None:
        """
        8. generate benchmark config file.
        :return: None
        """
        docker_addr = []
        for host in self.host_addr:
            docker_addr.append("http://{}:{}/all".format(host, self.docker_port))
        benchmark_config_preview = {
            'test': {
                'name': self.benchmark,
                'description': 'This is a {} benchmark of FISCO BCOS for caliper'.format(self.benchmark),
                'workers': {
                    'type': 'local',
                    'number': self.worker_num
                },
                'rounds': []
            },
            'monitor': {
                'interval': 5,
                'type': [
                    'docker'
                ],
                'docker': {
                    'containers': docker_addr
                }
            }
        }
        if self.docker_monitor is False:
            benchmark_config_preview = {
                'test': {
                    'name': self.benchmark,
                    'description': 'This is a {} benchmark of FISCO BCOS for caliper'.format(self.benchmark),
                    'workers': {
                        'type': 'local',
                        'number': self.worker_num
                    },
                    'rounds': []
                }
            }
        benchmark_rounds = {}
        for i in ['get', 'set', 'addUser', 'transfer']:
            benchmark_rounds[i] = {
                    'label': i,
                    'description': 'Test performance of {}ting name'.format(i),
                    'txNumber': self.tx_num,
                    'rateControl': {
                        'type': 'fixed-rate',
                        'opts': {
                            'tps': self.tx_speed
                        }
                    },
                    'callback': 'benchmarks/{benchmark}/{contract_type}/{i}.js'.format(
                        benchmark=self.benchmark, contract_type=self.contract_type, i=i)
                }
            if i == 'transfer':
                benchmark_rounds[i]['arguments'] = {'txnPerBatch': self.tx_per_batch}
        if self.benchmark == 'helloworld':
            benchmark_config_preview['test']['rounds'].append(benchmark_rounds['get'])
            benchmark_config_preview['test']['rounds'].append(benchmark_rounds['set'])
        if self.benchmark == 'transfer':
            benchmark_config_preview['test']['rounds'].append(benchmark_rounds['addUser'])
            benchmark_config_preview['test']['rounds'].append(benchmark_rounds['transfer'])
        with open("benchmarks/{benchmark}/{contract_type}/config.yaml".format(
                benchmark=self.benchmark, contract_type=self.contract_type), "w") as config:
            benchmark_config = dump(benchmark_config_preview)
            self.logger.debug(benchmark_config)
            config.write(benchmark_config)
        self.logger.debug("benchmark config file generated.")
        self.logger.info("### 8. generate benchmark config file ###")

    def run_task(self, cmd: str, desc: str, total: int) -> None:
        """
        pack command with tqdm progress bar.
        :param cmd: command
        :param desc: description
        :param total: total number of output Bytes
        :return: None
        """
        self.logger.info(desc + " test info: " +
            str({"tx_num": self.tx_num, "tx_speed": self.tx_speed,
                 "worker_num": self.worker_num,
                 "benchmark": self.benchmark,
                 "contract_type": self.contract_type,
                 "block_tx_num": self.block_tx_num,
                 "epoch_block_num": self.epoch_block_num,
                 "consensus_type": self.consensus_type,
                 "consensus_timeout": self.consensus_timeout,
                 "sealer_num": self.sealer_num,
                 "epoch_sealer_num": self.epoch_sealer_num,
                 "storage_type": self.storage_type,
                 "state_type": self.state_type,
                 "host_num": len(self.host_addr),
                 "node_num": self.node_num,
                 "tx_per_batch": self.tx_per_batch,
                 "node_bandwidth_limit": self.node_outgoing_bandwidth,
                 "host_addr": self.host_addr}))
        if self.nohup:
            try:
                subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL)  # must allow sterr
            except subprocess.CalledProcessError as e:
                self.logger.error("run task failed. retrying......")
                sys.stderr.write(
                    "common::run_command() : [ERROR]: output = %s, error code = %s , retrying...\n"
                    % (e.output, e.returncode))
                # retry
                time.sleep(10)
                # escape from too many printed info
                try:
                    subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL)  # must allow sterr
                except subprocess.CalledProcessError as e:
                    self.logger.error("run task failed. stopped......")
                    sys.stderr.write(
                        "common::run_command() : [ERROR]: output = %s, error code = %s , stopped...\n"
                        % (e.output, e.returncode))
                    raise subprocess.CalledProcessError(0, cmd)
        else:
            try:
                with tqdm(unit='B', unit_scale=True, miniters=1, desc=desc, total=total) as t:
                    process = subprocess.Popen(cmd, shell=True, bufsize=1, universal_newlines=True,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    # print subprocess output line-by-line as soon as its stdout buffer is flushed in Python 3:
                    for line in process.stdout:
                        t.update()
                        # forces stdout to "flush" the buffer
                        sys.stdout.flush()
                    process.stdout.close()
                    return_code = process.wait()
                    if return_code != 0:
                        raise subprocess.CalledProcessError(return_code, cmd)
            except subprocess.CalledProcessError as e:
                self.logger.error("run task failed. retrying......")
                sys.stderr.write(
                    "common::run_command() : [ERROR]: output = %s, error code = %s\n"
                    % (e.output, e.returncode))
                # retry
                time.sleep(10)
                try:
                    subprocess.check_call(cmd, shell=True)
                except subprocess.CalledProcessError as e:
                    self.logger.error("run task failed. stopped......")
                    sys.stderr.write(
                        "common::run_command() : [ERROR]: output = %s, error code = %s , stopped...\n"
                        % (e.output, e.returncode))
                    raise subprocess.CalledProcessError(0, cmd)

    def test(self) -> None:
        """
        9. auto benchmark test.
        need git clone, nvm use 8 && npm install
        :return: None
        """
        os.putenv("PATH", ":".join([os.getenv("PATH"), self.node_bin_path]))
        # benchmark command
        benchmark_command = "npx caliper launch master"
        benchmark_workspace = "--caliper-workspace ./"
        benchmark_config = "--caliper-benchconfig ./benchmarks/{benchmark}/{contract_type}/config.yaml".format(
            benchmark=self.benchmark, contract_type=self.contract_type)
        benchmark_network = "--caliper-networkconfig {}".format(self.network_config_file_path)
        self.logger.debug("auto benchmark started.")
        # print(' '.join([benchmark_command, benchmark_workspace, benchmark_config, benchmark_network]))
        self.run_task(' '.join([benchmark_command, benchmark_workspace, benchmark_config, benchmark_network]),
                      "{} host(s) {} nodes".format(len(self.host_addr), self.node_num),
                      80 + self.worker_num * 28 + self.node_num * 6)
        self.logger.info("### 9.0 auto benchmark test ###")

    def gen_results(self) -> tuple:
        """
        9.1 generate results from caliper log file.
        :return: test_time, result1, result2
        """
        # check if caliper log file is valid
        caliper_modify_time = datetime.fromtimestamp(os.path.getmtime('./caliper.log'))
        benchmark_file_time = datetime.fromtimestamp(
            os.path.getmtime('./benchmarks/{benchmark}/{contract_type}/config.yaml'.format(
                benchmark=self.benchmark, contract_type=self.contract_type)))
        if caliper_modify_time < benchmark_file_time:
            raise Exception("Please check this benchmark and caliper log now.[node_num: {}, host_num: {}, cons_typ: {}]"
                            .format(self.node_num, len(self.host_addr), self.consensus_type))
        # generate results
        pattern_get = re.compile(
            r"\| get\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|",
            re.I | re.S)
        pattern_set = re.compile(
            r"\| set\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|",
            re.I | re.S)
        pattern_add_user = re.compile(
            r"\| addUser\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|",
            re.I | re.S)
        pattern_transfer = re.compile(
            r"\| transfer\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|",
            re.I | re.S
        )
        pattern_datetime = re.compile(r"(\d*).(\d*).(\d*)-(\d*):(\d*):(\d*)\.(\d*)\[32m info \[39m \[caliper] \["
                                      r"report-builder] 	### All test results ###", re.I | re.S)
        set_result_final = ""
        get_result_final = ""
        add_user_result_final = ""
        transfer_result_final = ""
        datetime_result_final = ""
        try:
            with open('caliper.log', 'r') as caliper:
                line = caliper.readline()
                while line:
                    set_result = pattern_set.match(line)
                    get_result = pattern_get.match(line)
                    add_user_result = pattern_add_user.match(line)
                    transfer_result = pattern_transfer.match(line)
                    datetime_result = pattern_datetime.match(line)
                    if get_result is not None:
                        get_result_final = get_result.groups()
                        self.logger.debug(str(get_result_final))
                    if set_result is not None:
                        set_result_final = set_result.groups()
                        self.logger.debug(set_result_final)
                    if add_user_result is not None:
                        add_user_result_final = add_user_result.groups()
                        self.logger.debug(add_user_result_final)
                    if transfer_result is not None:
                        transfer_result_final = transfer_result.groups()
                        self.logger.debug(transfer_result_final)
                    if datetime_result is not None:
                        test_datetime = [int(datetime_result.group(i)) for i in range(1, 7)]
                        test_datetime = datetime(*test_datetime)  # func params deconstruct
                        datetime_result_final = test_datetime
                        self.logger.debug(str(datetime_result_final))
                    line = caliper.readline()
        except FileNotFoundError:
            self.logger.error('./caliper.log not found.')
        self.logger.info("### 9.1 generate results from caliper log file ###")
        if self.benchmark == 'helloworld':
            return datetime_result_final, get_result_final, set_result_final
        if self.benchmark == 'transfer':
            return datetime_result_final, add_user_result_final, transfer_result_final

    def caliper_history(self, test_datetime: datetime) -> None:
        """
        10. only collect caliper.log & report.html once after a test.
        :param test_datetime: datetime of this test process
        :return: None
        """
        if not os.path.exists('./caliper_history/log'):
            # fix: makedirs instead of mkdir
            os.makedirs('./caliper_history/log')
        if not os.path.exists('./caliper_history/report'):
            os.makedirs('./caliper_history/report')
        try:
            shutil.copyfile("./report.html", "./caliper_history/report/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S")
                            + " report.html")
        except FileNotFoundError:
            pass
        try:
            shutil.copyfile("./caliper.log", "./caliper_history/log/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S")
                            + " caliper.log")
        except FileNotFoundError:
            pass
        self.logger.info("### 10 collect caliper.log & report.html after a test ###")

    def add_data(self, test_datetime, result1, result2) -> None:
        """
        11. add data to data.csv
        :param test_datetime: test datetime
        :param result1: get/add_user performance result
        :param result2: set/tranfer performance result
        :return: None
        """
        try:
            with open("{}.csv".format(self.data_file_name), 'r', newline='') as data_csv:
                has_header = csv.Sniffer().has_header(data_csv.readline())
        except FileNotFoundError:
            has_header = False
        finally:
            pass
        with open("{}.csv".format(self.data_file_name), 'a', newline='') as data_csv:
            fields = ["datetime", "tx_num", "tx_speed", "tx_send_rate", "worker_num", "evaluation_label", "contract_type",
                      "block_tx_num", "epoch_block_num", "consensus_type", "consensus_timeout", "sealer_num",
                      "epoch_sealer_num", "storage_type", "state_type", "host_num", "node_num", "node_bandwidth_limit",
                      "hardware_id", "tx_per_batch", "succeed_num", "fail_num", "max_latency", "min_latency", "avg_latency",
                      "throughput"]
            writer = csv.DictWriter(data_csv, fieldnames=fields)
            if not has_header:
                writer.writeheader()
            result = {}
            if self.benchmark == 'helloworld':
                result = {"get": result1, "set": result2}
            if self.benchmark == 'transfer':
                result = {"addUser": result1, "transfer": result2}
            for r in result:
                data = {
                    "datetime": str(test_datetime),
                    "tx_num": self.tx_num,
                    "tx_speed": self.tx_speed,
                    "tx_send_rate": result[r][2],
                    "worker_num": self.worker_num,
                    "evaluation_label": r,
                    "contract_type": self.contract_type,
                    "block_tx_num": self.block_tx_num,
                    "epoch_block_num": self.epoch_block_num,
                    "consensus_type": self.consensus_type,
                    "consensus_timeout": self.consensus_timeout,
                    "sealer_num": self.sealer_num,
                    "epoch_sealer_num": self.epoch_sealer_num,
                    "storage_type": self.storage_type,
                    "state_type": self.state_type,
                    "host_num": len(self.host_addr),
                    "node_num": self.node_num,
                    "node_bandwidth_limit": self.node_outgoing_bandwidth,
                    "hardware_id": '{}-{}-{}'.format(self.hardware_flag, len(self.host_addr),
                                                     hashlib.md5(str(self.host_addr).encode('utf8')).hexdigest()[:8]),
                    "tx_per_batch": self.tx_per_batch,
                    "succeed_num": result[r][0],
                    "fail_num": result[r][1],
                    "max_latency": result[r][3],
                    "min_latency": result[r][4],
                    "avg_latency": result[r][5],
                    "throughput": result[r][6]
                }
                writer.writerow(data)
        self.logger.info("### 11. add data to data.csv ###")

    def __add_hardware_data(self) -> None:
        """
        12. add hardware data. TODO: hardware data
        :return: None
        """
        # check if hardware changed: flag-ip-md5[:8]
        CSV_FILE_PATH = './data_hardware.csv'
        if os.path.exists(CSV_FILE_PATH):
            hardware_data = pd.read_csv(CSV_FILE_PATH)
            hardware_ids = hardware_data['id'].drop_duplicates()
            hardware_id = '{}-{}-{}'.format(self.hardware_flag, len(self.host_addr),
                                            hashlib.md5(str(self.host_addr).encode('utf8'))[:8])
            if hardware_id in hardware_ids.values:
                return None
        # write new id
        for host in self.host_addr:
            ssh = SSH(host, 'root', self.root_password)
            linux_issue_version = ssh.exec_command('head -n 1 /etc/issue').strip()
            # out = ssh.exec_command('cat /proc/cpuinfo | grep name | cut -f2 -d: | uniq -c')
            # cpu & logical number: ('2', 'Intel(R) Core(TM) i7-8559U CPU @ 2.70GHz')
            # system_cpu_logical = re.match('\s*(\d*)\s*(.*)', out).groups()
            out = ssh.exec_command("cat /proc/cpuinfo | grep 'model name' | uniq | awk -F: '{print $2}'")  # list
            cpu_model = out.strip()
            out = ssh.exec_command('cat /proc/cpuinfo | grep "processor" | wc -l')
            cpu_logical_core_num = int(out)
            # out = ssh.exec_command('cat /proc/cpuinfo | grep physical | uniq -c')
            # cpu & physical number: ['1', '1'] means 2 logical core 2 physical core
            out = ssh.exec_command('cat /proc/cpuinfo | grep "physical id" | sort | uniq | wc -l')
            cpu_physical_core_num = int(out)
            out = ssh.exec_command("cat /proc/cpuinfo | grep 'cpu MHz' | uniq | awk -F: '{print $2}'")
            # multiple
            cpu_mhz = out.strip()
            out = ssh.exec_command("cat /proc/cpuinfo | grep 'cache size' | uniq | awk -F: '{print $2}'")
            cpu_cache_size = out.strip()
            out = ssh.exec_command("cat /proc/meminfo | grep MemTotal | awk -F: '{print $2}'")
            mem_total_kb = re.match(r'\s*(\d*)\s*kB', out).group(1)
            if self.disk_type == 'normal':
                out = ssh.exec_command("smartctl --all /dev/sda | grep 'User Capacity' | awk -F: '{print $2}'")
                disk_capacity_gb = float(re.match(r'.*\[(\d*\.?\d*)\s*GB]', out).group(1))
                disk_model = 'hdparm -t /dev/sda'
                # multiple test avg
            if self.disk_type == 'raid':
                out = ssh.exec_command("")
            # disk model

    def __test_once_pre(self) -> None:
        """
        one more step before test blockchain once, acquire data once.
        :return: None
        """
        self.clean()
        self.check_parameters()
        self.gen_nodes()
        self.ch_group_config()
        self.ch_node_config()
        self.gen_docker_scripts()
        self.copy_nodes_to_all_host()
        self.gen_network_config()
        self.gen_benchmark_config()
        self.test()
        test_datetime, get_result, set_result = self.gen_results()
        self.caliper_history(test_datetime)
        self.add_data(test_datetime, get_result, set_result)

    def test_once(self) -> None:
        """
        test blockchain once, acquire data once.
        :return: None
        """
        try:
            self.__test_once_pre()
        except Exception:
            self.logger.info("AutoBench Test[ERROR]: something wrong, try again after 60s[1].\n")
            time.sleep(60)
            try:
                self.__test_once_pre()
            except Exception:
                self.logger.info("AutoBench Test[ERROR]: something wrong, try again after 60s[2].\n")
                time.sleep(60)
                try:
                    self.__test_once_pre()
                except Exception:
                    self.logger.info("AutoBench Test[ERROR]: something wrong, cannot test this config, mark down[-].\n")
                    test_datetime = datetime.now()
                    get_result = ('-', '-', '-', '-', '-', '-', '-')
                    set_result = ('-', '-', '-', '-', '-', '-', '-')
                    self.caliper_history(test_datetime)
                    self.add_data(test_datetime, get_result, set_result)


if __name__ == '__main__':
    print("Sample: ")
    print("""from autobench import AutoBench\n
autobench = AutoBench("/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/",
                      ["192.168.177.153", "192.168.177.154"])
autobench.test_once()
    """)
