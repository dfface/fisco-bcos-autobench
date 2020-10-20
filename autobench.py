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

# test steps:
# 0 hardware is ready
# 1 set system settings (only once)
# 2 set test options
# 3 run this script


class AutoBench(object):

    def __init__(self, node_bin_path: str, host_addr: list, root_password='123456', consensus_type='pbft',
                 storage_type='rocksdb', tx_num=10000, tx_speed=1000, block_tx_num=1000, epoch_sealer_num=4,
                 consensus_timeout=3, epoch_block_num=1000, node_num=4, sealer_num=4, worker_num=1,
                 node_outgoing_bandwidth=0, group_flag=1, agency_flag='dfface',
                 network_config_file_path='./network/fisco-bcos.json',
                 benchmark_config_file_path='./benchmark/config.yaml',
                 ipconfig_file_path='./network/ipconfig', p2p_start_port=30300,
                 channel_start_port=20200, jsonrpc_start_port=8545,
                 contract_type='solidity', state_type='storage', contract_path='./smart_contracts/HelloWorld.sol',
                 log_level=logging.ERROR):
        """
        initialize an AutoBench instance.
        :param node_bin_path: use command 'which npm' then you find the bin path
        :param host_addr: the host address of each server
        :param root_password: must be root's password, PermitRootLogin yes (keep consistent with all hosts)
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
        :param network_config_file_path: the path of network config file
        :param benchmark_config_file_path: the path of benchmark config file
        :param ipconfig_file_path: the path of ipconfig file
        :param p2p_start_port: the start port of p2p
        :param channel_start_port: the start port of channel
        :param jsonrpc_start_port: the start port of jsonrpc
        :param contract_type: must be solidity/precompiled
        :param state_type: must be storage TODO: mpt
        :param contract_path: the path of smart contract
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
        self.contract_type = contract_type
        self.contract_path = contract_path
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
        # 3 optional settings(better not to change)
        self.group_flag = group_flag
        self.agency_flag = agency_flag
        self.network_config_file_path = network_config_file_path
        self.benchmark_config_file_path = benchmark_config_file_path
        self.ipconfig_file_path = ipconfig_file_path
        self.p2p_start_port = p2p_start_port
        self.channel_start_port = channel_start_port
        self.jsonrpc_start_port = jsonrpc_start_port
        # 4 predefined variables
        self.node_assigned = []  # balance nodes on hosts (many functions may use)
        # 5 log settings
        self.logger = logging.getLogger('AutoBench')
        self.logger.setLevel(logging.DEBUG)  # must set this
        log_format = logging.Formatter('%(asctime)s - %(name)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        file_handler = logging.FileHandler('./autobench.log', 'a', 'utf-8')
        file_handler.setFormatter(log_format)
        file_handler.setLevel(logging.INFO)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        console_handler.setLevel(log_level)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        # 6 check constraints
        self.__check_parameters()

    def __check_parameters(self) -> None:
        """
        1. check parameters' constraints before every test.
        :return: None
        """
        assert self.node_num >= self.sealer_num
        assert self.node_num >= len(self.host_addr)
        if self.contract_type == "rpbft":
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

    def __gen_nodes(self) -> str:
        """
        2. generate nodes folder.
        :return: ipconfig_string
        """
        ipconfig_string = ""  # ipconfig file content
        host_num = len(self.host_addr)
        node_num_avg = int(self.node_num / host_num)
        node_num_remain = self.node_num % host_num
        self.node_assigned = [node_num_avg] * (host_num - node_num_remain) + [node_num_avg + 1] * node_num_remain
        for index, host in enumerate(self.host_addr):
            ipconfig_string += "{}:{} {} {} {},{},{}\n".format(host, self.node_assigned[index], self.agency_flag,
                                                               self.group_flag, self.p2p_start_port,
                                                               self.channel_start_port, self.jsonrpc_start_port)
        self.logger.info("ipconfig file generated.\n" + ipconfig_string)
        with open(self.ipconfig_file_path, "w") as ipconfig:
            ipconfig.write(ipconfig_string)
        node_gen_command = "bash ./network/build_chain.sh -o ./network/nodes -T -f {} -d -i -s {} -c {}".format(
            self.ipconfig_file_path, self.storage_type, self.consensus_type)
        node_generated_result = subprocess.getoutput(node_gen_command)
        self.logger.debug(node_generated_result)
        self.logger.info("nodes folder generated.")
        return ipconfig_string

    def __ch_group_config(self) -> None:
        """
        3. change group.1.genesis file of each node.
        """
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
                sealer_node = re.match(r"\s*node.(\d)=.*", line_to_write)
                if sealer_node:
                    # change sealers(consensusers) to sealer_num
                    if int(sealer_node.group(1)) >= self.sealer_num:
                        line_to_write = ""
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
        self.logger.info("group config files of each node have changed.")

    def __ch_node_config(self) -> None:
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
                        if self.node_outgoing_bandwidth > 0:
                            line_to_write = re.sub(r"\s*;outgoing_bandwidth_limit=2",
                                                   "    outgoing_bandwidth_limit=" +
                                                   str(self.node_outgoing_bandwidth), line)
                            node_config_bk.write(line_to_write)
                        else:
                            node_config_bk.write(line)
                os.remove(node_ini_path)
                os.rename(node_ini_path + ".bk", node_ini_path)
        self.logger.info("node config file generated.")

    def __gen_docker_scripts(self) -> tuple:
        """
        5. generate start & stop scripts.
        :return: start_all_string, stop_all_string
        """
        start_all_string = ""
        stop_all_string = ""
        for index, host in enumerate(self.host_addr):
            for i in range(0, self.node_assigned[index]):
                start_all_string += "docker -H {host}:2375 run -d --rm --name node{i} " \
                                    "-v /data/nodes/{host}/node{i}/:/data -p {p2p_port}:{p2p_port} " \
                                    "-p {channel_port}:{channel_port} -p {jsonrpc_port}:{jsonrpc_port} " \
                                    "-w=/data fiscoorg/fiscobcos:latest -c config.ini 1> /dev/null && echo " \
                                    "\"\033[32mremote {host} container node{i} started\033[0m\"\n"\
                    .format(host=host, i=i, p2p_port=self.p2p_start_port + i, channel_port=self.channel_start_port + i,
                            jsonrpc_port=self.jsonrpc_start_port + i)
                stop_all_string += "docker -H {host}:2375 stop $(docker -H {host} ps -a | grep node{i} | " \
                                   "cut -d \" \" -f 1) 1> /dev/null && echo \"\033[32mremote {host} container " \
                                   "node{i} stopped\033[0m\"\n".format(host=host, i=i)
        with open("./network/nodes/start_all.sh", "w") as start_all:
            start_all.write(start_all_string)
        with open("./network/nodes/stop_all.sh", "w") as stop_all:
            stop_all.write(stop_all_string)
        os.chmod("./network/nodes/start_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
        os.chmod("./network/nodes/stop_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
        self.logger.info("start_all.sh & stop_all.sh file generated.")
        return start_all_string, stop_all_string

    def __copy_nodes_to_all_host(self) -> None:
        """
        6. copy nodes to all hosts: need sshpass, openssh-server, root login, /data full privileges
        :return: None
        """
        for host in self.host_addr:
            copy_result = subprocess.getoutput("sshpass -p {password} scp -r network/nodes/ root@{host}:/data/"
                                               .format(password=self.root_password, host=host))
            self.logger.debug(copy_result + "copy to {} /data/nodes".format(host))
        self.logger.info("copy nodes to all hosts finished.")

    def __gen_network_config(self) -> None:
        """
        7. generate network config file.
        :return: None
        """
        nodes_json = []
        nodes_count = 0
        for index, host in enumerate(self.host_addr):
            if nodes_count >= self.sealer_num:
                break
            for i in range(0, self.node_assigned[index]):
                if nodes_count >= self.sealer_num:
                    break
                node_json = {"ip": host, "rpcPort": str(self.jsonrpc_start_port + i),
                             "channelPort": str(self.channel_start_port + i)}
                nodes_json.append(node_json)
                nodes_count += 1
        network_config_json = {
            "caliper": {
                "blockchain": "fisco-bcos",
                "command": {
                    "start": "network/nodes/start_all.sh; sleep 3s",
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
                        "path": self.contract_path,
                        "language": self.contract_type,
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
        self.logger.info("network config file generated.")

    def __gen_benchmark_config(self) -> None:
        """
        8. generate benchmark config file.
        :return: None
        """
        docker_addr = ""
        for host in self.host_addr:
            docker_addr += "    - http://{}:2375/all\n".format(host)
        generate_time = datetime.now()
        benchmark_config_string = """# benchmark config\n# author: {agency_flag}\n# time: {generate_time}\n
---
test:
  name: Hello World
  description: This is a helloworld benchmark of FISCO BCOS for caliper
  workers:
    type: local
    number: {worker_num}
  rounds:
  - label: get
    description: Test performance of getting name
    txNumber: {tx_num}
    rateControl:
      type: fixed-rate
      opts:
        tps: {tx_speed}
    callback: benchmark/get.js
  - label: set
    description: Test performance of setting name
    txNumber: {tx_num}
    rateControl:
      type: fixed-rate
      opts:
        tps: {tx_speed}
    callback: benchmark/set.js
monitor:
  interval: 1
  type:
  - docker
  docker:
    containers:
{docker_addr}
""".format(agency_flag=self.agency_flag, generate_time=generate_time, tx_num=self.tx_num,
           tx_speed=self.tx_speed, worker_num=self.worker_num, docker_addr=docker_addr)
        with open(self.benchmark_config_file_path, "w") as config:
            config.write(benchmark_config_string)
        self.logger.info("benchmark config file generated.")

    @classmethod
    def run_task(cls, cmd: str, desc: str, total: int) -> None:
        """
        pack command with tqdm progress bar.
        :param cmd: command
        :param desc: description
        :param total: total number of output Bytes
        :return: None
        """
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
            sys.stderr.write(
                "common::run_command() : [ERROR]: output = %s, error code = %s\n"
                % (e.output, e.returncode))

    def __test(self) -> None:
        """
        9. auto benchmark test.
        need git clone, nvm use 8 && npm install
        :return: None
        """
        os.putenv("PATH", ":".join([os.getenv("PATH"), self.node_bin_path]))
        # benchmark command
        benchmark_command = "npx caliper launch master"
        benchmark_workspace = "--caliper-workspace ./"
        benchmark_config = "--caliper-benchconfig {}".format(self.benchmark_config_file_path)
        benchmark_network = "--caliper-networkconfig {}".format(self.network_config_file_path)
        self.logger.info("auto benchmark started.")
        AutoBench.run_task(' '.join([benchmark_command, benchmark_workspace, benchmark_config, benchmark_network]),
                           "auto benchmark {} host(s) {} nodes".format(len(self.host_addr), self.node_num),
                           80 + self.worker_num * 28 + self.node_num * 6)

    def __gen_results(self) -> tuple:
        """
        9.1 generate results from caliper log file.
        :return: test_time, get_result, set_result
        """
        # check if caliper log file is valid
        caliper_modify_time = datetime.fromtimestamp(os.path.getmtime('./caliper.log'))
        benchmark_file_time = datetime.fromtimestamp(os.path.getmtime(self.benchmark_config_file_path))
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
        pattern_datetime = re.compile(r"(\d*).(\d*).(\d*)-(\d*):(\d*):(\d*)\.(\d*)\[32m info \[39m \[caliper] \["
                                      r"report-builder] 	### All test results ###", re.I | re.S)
        set_result_final = ""
        get_result_final = ""
        datetime_result_final = ""
        try:
            with open('caliper.log', 'r') as caliper:
                line = caliper.readline()
                while line:
                    set_result = pattern_set.match(line)
                    get_result = pattern_get.match(line)
                    datetime_result = pattern_datetime.match(line)
                    if get_result is not None:
                        get_result_final = get_result.groups()
                        self.logger.debug(str(get_result_final))
                    if set_result is not None:
                        set_result_final = set_result.groups()
                        self.logger.debug(set_result_final)
                    if datetime_result is not None:
                        test_datetime = [int(datetime_result.group(i)) for i in range(1, 7)]
                        test_datetime = datetime(*test_datetime)  # func params deconstruct
                        datetime_result_final = test_datetime
                        self.logger.debug(str(datetime_result_final))
                    line = caliper.readline()
        except FileNotFoundError:
            self.logger.error('./caliper.log not found.')
        self.logger.debug('results from caliper log as follows.\n' + str(get_result_final) + '\n'
                          + str(set_result_final) + '\n' + str(datetime_result_final))
        return datetime_result_final, get_result_final, set_result_final

    def __clean(self) -> None:
        """
        0. clean up before every test.
        need root & it's passwd, sshpass, openssh-server, PermitRootLogin
        :return: None
        """
        try:
            shutil.rmtree("network/nodes")
        except FileNotFoundError:
            pass
        finally:
            self.logger.info("network/nodes cleaned.")
        try:
            os.remove(self.ipconfig_file_path)
        except FileNotFoundError:
            pass
        finally:
            self.logger.info(self.ipconfig_file_path + " cleaned.")
        try:
            os.remove(self.network_config_file_path)
        except FileNotFoundError:
            pass
        finally:
            self.logger.info(self.network_config_file_path + " cleaned.")
        try:
            os.remove(self.benchmark_config_file_path)
        except FileNotFoundError:
            pass
        finally:
            self.logger.info(self.benchmark_config_file_path + " cleaned.")
        try:
            os.remove("./caliper.log")
        except FileNotFoundError:
            pass
        finally:
            self.logger.info("./caliper.log cleaned.")
        try:
            os.remove("./report.html")
        except FileNotFoundError:
            pass
        finally:
            self.logger.info("./report.html cleaned.")
        self.logger.info("project cleaned.")
        try:
            os.remove("./smart_contracts/HelloWorld.address")
        except FileNotFoundError:
            pass
        finally:
            self.logger.info("./smart_contracts/HelloWorld.address cleaned.")
        for host in self.host_addr:
            remove_result = subprocess.getoutput("sshpass -p {password} ssh root@{host} 'rm -rf /data/nodes'"
                                                 .format(password=self.root_password, host=host))
            self.logger.info(remove_result + "{}: /data/nodes removed.".format(host))

    @staticmethod
    def caliper_history(test_datetime: datetime) -> None:
        """
        10. only collect caliper.log & report.html once after a test.
        :param test_datetime: datetime of this test process
        :return: None
        """
        shutil.copyfile("./report.html", "./caliper_history/report/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S")
                        + " report.html")
        shutil.copyfile("./caliper.log", "./caliper_history/log/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S")
                        + " caliper.log")

    def __add_data(self, test_datetime, get_result, set_result) -> None:
        """
        11. add data to data.csv
        :param test_datetime: test datetime
        :param get_result: get performance result
        :param set_result: set performance result
        :return: None
        """
        try:
            with open("data.csv", 'r', newline='') as data_csv:
                has_header = csv.Sniffer().has_header(data_csv.readline())
        except FileNotFoundError:
            has_header = False
        finally:
            pass
        with open("data.csv", 'a', newline='') as data_csv:
            fields = ["datetime", "tx_num", "tx_send_rate", "worker_num", "evaluation_label", "contract_type",
                      "block_tx_num", "epoch_block_num", "consensus_type", "consensus_timeout", "sealer_num",
                      "epoch_sealer_num", "storage_type", "state_type", "host_num", "node_num", "node_bandwidth_limit",
                      "succeed_num", "fail_num", "max_latency", "min_latency", "avg_latency", "throughput"]
            writer = csv.DictWriter(data_csv, fieldnames=fields)
            if not has_header:
                writer.writeheader()
            result = {"get": get_result, "set": set_result}
            for r in result:
                data = {
                    "datetime": str(test_datetime),
                    "tx_num": self.tx_num,
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
                    "succeed_num": result[r][0],
                    "fail_num": result[r][1],
                    "max_latency": result[r][3],
                    "min_latency": result[r][4],
                    "avg_latency": result[r][5],
                    "throughput": result[r][6]
                }
                writer.writerow(data)

    def test_once(self) -> None:
        """
        test blockchain once, acquire data once.
        :return: None
        """
        self.__clean()
        self.__check_parameters()
        self.__gen_nodes()
        self.__ch_group_config()
        self.__ch_node_config()
        self.__gen_docker_scripts()
        self.__copy_nodes_to_all_host()
        self.__gen_network_config()
        self.__gen_benchmark_config()
        self.__test()
        test_datetime, get_result, set_result = self.__gen_results()
        self.caliper_history(test_datetime)
        self.__add_data(test_datetime, get_result, set_result)


if __name__ == '__main__':
    print("Sample: ")
    print("""from autobench import AutoBench\n
autobench = AutoBench("/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/",
                      ["192.168.177.153", "192.168.177.154"])
autobench.test_once()
    """)
