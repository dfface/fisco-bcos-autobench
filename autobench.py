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

# test steps:
# 0 hardware is ready
# 1 set system settings (only once)
# 2 set test options
# 3 run this script

# 1 system settings
node_bin_path = "/Users/yuhanliu/.nvm/versions/node/v8.17.0/bin/"  # 'which npm' then you find the bin path
username = "root"  # host's ssh login username (keep consistent with all hosts)
password = "123456"  # host's ssh login password (keep consistent with all hosts)
root_password = "123456"  # must be root's password, PermitRootLogin yes (keep consistent with all hosts)
# 2 test options
consensus_type = "pbft"  # (pbft raft rpbft)
storage_type = "rocksdb"  # (rocksdb mysql external scalable)
tx_num = 10000  # the total number of transactions
tx_speed = 5000  # the max speed of sending transactions (tps)
block_tx_num = 2000  # the max number of transactions of a block
epoch_sealer_num = 2  # the working sealers num of each consensus epoch
consensus_timeout = 3  # in seconds, block consensus timeout, at least 3s
epoch_block_num = 1000  # the number of generated blocks each epoch
host_addr = ["192.168.177.153", "192.168.177.154"]  # the host address of each server
node_num = 5  # the total num of nodes (sealer & follower)
sealer_num = 5  # the total num of sealer nodes (consensusers)
# better not to change
worker_num = 5  # specifies the number of worker processes to use for executing the workload (caliper)
node_outgoing_bandwidth = 0  # 0 means no limit
group_flag = 1  # the group includes all nodes
agency_flag = "dfface"  # the agency name
network_config_file_path = "./network/fisco-bcos.json"
benchmark_config_file_path = "./benchmark/config.yaml"
ipconfig_file_path = "./network/ipconfig"
p2p_start_port = 30300
channel_start_port = 20200
jsonrpc_start_port = 8545
contract_type = "solidity"
state_type = "storage"
# predefined variables
node_gen_command = "bash ./network/build_chain.sh -o ./network/nodes -T -f {} -d -i -s {} -c {}".format(ipconfig_file_path, storage_type, consensus_type)
node0_genesis_path = "./network/nodes/{}/node0/conf/group.{}.genesis".format(host_addr[0], group_flag)
node0_ini_path = "./network/nodes/{}/node0/config.ini".format(host_addr[0])
host_num = len(host_addr)  # host num
node_assigned = []  # balance nodes on hosts (many functions may use)
# log config
logging.basicConfig(format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s', level=logging.INFO)


def check():
    """
      check constraints before every test.
    :return: 1
    """
    assert node_num >= sealer_num
    assert node_num >= host_num
    assert sealer_num >= epoch_sealer_num
    assert consensus_type in ["pbft", "raft", "rpbft"]
    assert storage_type in ["rocksdb", "mysql", "external", "scalable"]
    assert tx_num > 0
    assert tx_speed > 0
    assert block_tx_num > 0
    assert epoch_sealer_num > 0
    assert consensus_timeout >= 3
    assert epoch_block_num > 0
    assert host_num > 0
    assert node_num > 0
    assert sealer_num > 0
    assert worker_num > 0
    assert node_outgoing_bandwidth >= 0
    assert group_flag == 1
    return 1


def gen_nodes():
    """
    generate nodes folder.
    :return: 1
    """
    global node_assigned
    ipconfig_string = ""  # ipconfig file content
    node_num_avg = int(node_num / host_num)
    node_num_remain = node_num % host_num
    node_assigned = [node_num_avg] * (host_num - node_num_remain) + [node_num_avg + 1] * node_num_remain
    for index, host in enumerate(host_addr):
        ipconfig_string += "{}:{} {} {} {},{},{}\n".format(host, node_assigned[index], agency_flag, group_flag,
                                                           p2p_start_port, channel_start_port, jsonrpc_start_port)
    logging.info("ipconfig file generated.\n" + ipconfig_string)
    with open(ipconfig_file_path, "w") as ipconfig:
        ipconfig.write(ipconfig_string)
    node_generated_result = subprocess.getoutput(node_gen_command)
    logging.debug(node_generated_result)
    logging.info("nodes generated.")
    return 1


def ch_group_config():
    """
    change group.1.genesis file of each node.
    :return: 1
    """
    with open(node0_genesis_path, "r") as group_config,\
            open(node0_genesis_path + '.bk', "w") as group_config_bk:
        for line in group_config:
            line_to_write = re.sub(r"\s*max_trans_num=1000", "    max_trans_num=" + str(block_tx_num), line)
            line_to_write = re.sub(r"\s*epoch_sealer_num=3", "    epoch_sealer_num=" + str(epoch_sealer_num),
                                   line_to_write)
            line_to_write = re.sub(r"\s*consensus_timeout=3", "    consensus_timeout=" + str(consensus_timeout),
                                   line_to_write)
            line_to_write = re.sub(r"\s*epoch_block_num=1000", "    epoch_block_num=" + str(epoch_block_num),
                                   line_to_write)
            sealer_node = re.match(r"\s*node.(\d)=.*", line_to_write)
            if sealer_node:
                # change consensusers to sealer_num
                if int(sealer_node.group(1)) >= sealer_num:
                    line_to_write = ""
            group_config_bk.write(line_to_write)
    os.remove(node0_genesis_path)
    os.rename(node0_genesis_path + '.bk', node0_genesis_path)
    # copy group config to other nodes
    for index, host in enumerate(host_addr):
        for i in range(0, node_assigned[index]):
            if index == 0 and i == 0:
                continue
            node_genesis_path = "network/nodes/{}/node{}/conf/group.{}.genesis".format(host, i, group_flag)
            logging.debug("copy genesis file to " + node_genesis_path)
            os.remove(node_genesis_path)
            shutil.copy(node0_genesis_path, node_genesis_path)
    logging.info("group config file generated.")
    return 1


def ch_node_config():
    """
    change config.ini file of each node.
    :return: 1
    """
    # change node config of each node
    for index, host in enumerate(host_addr):
        for i in range(0, node_assigned[index]):
            node_ini_path = "network/nodes/{}/node{}/config.ini".format(host, i)
            logging.debug("change ini file " + node_ini_path)
            with open(node_ini_path, "r") as node_config, open(node_ini_path + '.bk', "w") as node_config_bk:
                for line in node_config:
                    if node_outgoing_bandwidth > 0:
                        line_to_write = re.sub(r"\s*;outgoing_bandwidth_limit=2",
                                               "    outgoing_bandwidth_limit=" + str(node_outgoing_bandwidth), line)
                        node_config_bk.write(line_to_write)
                    else:
                        node_config_bk.write(line)
            os.remove(node_ini_path)
            os.rename(node_ini_path + ".bk", node_ini_path)
    logging.info("node config file generated.")
    return 1


def gen_docker_scripts():
    """
    generate start & stop scripts.
    :return: 1
    """
    start_all_string = ""
    stop_all_string = ""
    for index, host in enumerate(host_addr):
        for i in range(0, node_assigned[index]):
            start_all_string += "docker -H {host}:2375 run -d --rm --name node{i} -v /data/nodes/{host}/node{i}/:/data " \
                                "-p {p2p_port}:{p2p_port} -p {channel_port}:{channel_port} -p {jsonrpc_port}:{jsonrpc_port} " \
                                "-w=/data fiscoorg/fiscobcos:latest -c config.ini 1> /dev/null && echo " \
                                "\"\033[32mremote {host} container node{i} started\033[0m\"\n".format(host=host, i=i,
                                                                                                      p2p_port=p2p_start_port + i,
                                                                                                      channel_port=channel_start_port + i,
                                                                                                      jsonrpc_port=jsonrpc_start_port + i)
            stop_all_string += "docker -H {host}:2375 stop $(docker -H {host} ps -a | grep node{i} | " \
                               "cut -d \" \" -f 1) 1> /dev/null && echo \"\033[32mremote {host} container node{i} " \
                               "stopped\033[0m\"\n".format(host=host, i=i)
    with open("network/nodes/start_all.sh", "w") as start_all:
        start_all.write(start_all_string)
    with open("network/nodes/stop_all.sh", "w") as stop_all:
        stop_all.write(stop_all_string)
    os.chmod("network/nodes/start_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
    os.chmod("network/nodes/stop_all.sh", stat.S_IXOTH | stat.S_IRWXG | stat.S_IRWXU)
    logging.info("start_all.sh & stop_all.sh file generated.")
    return 1


def copy_nodes_to_all_host():
    """
    copy nodes to all hosts: need sshpass, openssh-server, root login, /data full privileges
    :return: 1
    """
    for host in host_addr:
        copy_result = subprocess.getoutput("sshpass -p {password} scp -r network/nodes/ {username}@{host}:/data/"
                                           .format(password=password, username=username, host=host))
        logging.debug(copy_result + "copy to {} /data/nodes".format(host))
    logging.info("copy nodes to all hosts finished.")
    return 1


def gen_network_config():
    """
    generate network config file.
    :return: 1
    """
    nodes_json = []
    nodes_count = 0
    for index, host in enumerate(host_addr):
        if nodes_count >= sealer_num:
            break
        for i in range(0, node_assigned[index]):
            if nodes_count >= sealer_num:
                break
            node_json = {"ip": host, "rpcPort": str(jsonrpc_start_port + i), "channelPort": str(channel_start_port + i)}
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
                    "key": "./network/nodes/{}/sdk/node.key".format(host_addr[0]),
                    "cert": "./network/nodes/{}/sdk/node.crt".format(host_addr[0]),
                    "ca": "./network/nodes/{}/sdk/ca.crt".format(host_addr[0])
                },
                "groupID": group_flag,
                "timeout": 100000
            },
            "smartContracts": [
                {
                    "id": "helloworld",
                    "path": "smart_contracts/HelloWorld.sol",
                    "language": "solidity",
                    "version": "v0"
                }
            ]
        },
        "info": {
            "Version": "1.0.0",
            "Size": "{} Nodes".format(node_num),
            "Distribution": "{} Host(s)".format(host_num)
        }
    }
    with open(network_config_file_path, "w") as network_config:
        network_config.write(json.dumps(network_config_json))
    logging.info("network config file generated.")
    return 1


def gen_benchmark_config():
    """
    generate benchmark config file.
    :return: 1
    """
    docker_addr = ""
    for host in host_addr:
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
""".format(agency_flag=agency_flag, generate_time=generate_time, tx_num=tx_num,
           tx_speed=tx_speed, worker_num=worker_num, docker_addr=docker_addr)
    with open(benchmark_config_file_path, "w") as config:
        config.write(benchmark_config_string)
    logging.info("benchmark config file generated.")
    return 1


def run_task(cmd, desc, total):
    """
    pack command with tqdm
    :param cmd: command
    :param desc: description
    :param total: total number of output Bytes
    :return: command output
    """
    try:
        # create a default tqdm progress bar object, unit='B' definnes a String that will be used to define the unit of each iteration in our case bytes
        with tqdm(unit='B', unit_scale=True, miniters=1, desc=desc, total=total) as t:
            process = subprocess.Popen(cmd, shell=True, bufsize=1, universal_newlines=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            # print subprocess output line-by-line as soon as its stdout buffer is flushed in Python 3:
            output = ""
            for line in process.stdout:
                # Update the progress, since we do not have a predefined iterator
                # tqdm doesnt know before hand when to end and cant generate a progress bar
                # hence elapsed time will be shown, this is good enough as we know
                # something is in progress
                t.update()
                # forces stdout to "flush" the buffer
                sys.stdout.flush()
                output += line
            process.stdout.close()
            return_code = process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, cmd)
            return output
    except subprocess.CalledProcessError as e:
        sys.stderr.write(
            "common::run_command() : [ERROR]: output = %s, error code = %s\n"
            % (e.output, e.returncode))


def test():
    """
    auto benchmark test.
    need git clone, nvm use 8 && npm install
    :return: test_time, get_result, set_result
    """
    os.putenv("PATH", ":".join([os.getenv("PATH"), node_bin_path]))
    # benchmark command
    benchmark_command = "npx caliper launch master"
    benchmark_workspace = "--caliper-workspace ./"
    benchmark_config = "--caliper-benchconfig {}".format(benchmark_config_file_path)
    benchmark_network = "--caliper-networkconfig {}".format(network_config_file_path)
    logging.info("auto benchmark started.")
    output_string = run_task(' '.join([benchmark_command, benchmark_workspace, benchmark_config, benchmark_network]),
                             "auto benchmark {} host(s) {} nodes".format(host_num, node_num), 98 + worker_num * (19 + node_num * 3))
    logging.debug(output_string)
    # catch all test result
    pattern_results = re.compile(r"### All test results ###([\s\S]*)Generated report with path", re.M | re.I | re.S)
    searched = pattern_results.findall(output_string)
    # catch time
    pattern_time = re.compile(r"### All test results ###\n(\S*) info")
    test_time = pattern_time.findall(output_string)[0]
    pattern_datetime = re.compile(r"(\d*).(\d*).(\d*)-(\d*):(\d*):(\d*)\.(\d*)")
    test_datetime = pattern_datetime.match(test_time)
    test_datetime = [int(test_datetime.group(i)) for i in range(1, 7)]
    test_datetime = datetime(*test_datetime)
    logging.info("test time: " + str(test_datetime))
    logging.info("test result: (Succ, Fail, Send Rate(TPS), Max Latency(s), Min Latency(s), Avg Latency(s), Throughput(TPS))")
    # catch operation type: get/set
    pattern_get = re.compile(
        r"\n\| get  \|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|")
    pattern_set = re.compile(
        r"\n\| set  \|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|")
    get_result = pattern_get.findall(searched[0])[0]
    set_result = pattern_set.findall(searched[0])[0]
    logging.info("get :" + str(get_result))
    logging.info("set: " + str(set_result))
    return test_datetime, get_result, set_result


def clean():
    """
    clean up before every test.
    need root & it's passwd, sshpass, openssh-server, PermitRootLogin
    :return:
    """
    try:
        shutil.rmtree("network/nodes")
    except FileNotFoundError:
        pass
    finally:
        logging.info("network/nodes cleaned.")
    try:
        os.remove(ipconfig_file_path)
    except FileNotFoundError:
        pass
    finally:
        logging.info(ipconfig_file_path + " cleaned.")
    try:
        os.remove(network_config_file_path)
    except FileNotFoundError:
        pass
    finally:
        logging.info(network_config_file_path + " cleaned.")
    try:
        os.remove(benchmark_config_file_path)
    except FileNotFoundError:
        pass
    finally:
        logging.info(benchmark_config_file_path + " cleaned.")
    try:
        os.remove("./caliper.log")
    except FileNotFoundError:
        pass
    finally:
        logging.info("./caliper.log cleaned.")
    try:
        os.remove("./report.html")
    except FileNotFoundError:
        pass
    finally:
        logging.info("./report.html cleaned.")
    logging.info("project cleaned.")
    try:
        os.remove("./smart_contracts/HelloWorld.address")
    except FileNotFoundError:
        pass
    finally:
        logging.info("./smart_contracts/HelloWorld.address cleaned.")
    for host in host_addr:
        remove_result = subprocess.getoutput("sshpass -p {password} ssh {username}@{host} 'rm -rf /data/nodes'"
                                             .format(password=password, username="root", host=host))
        logging.info(remove_result + "{}: /data/nodes removed.".format(host))


def caliper_history(test_datetime):
    """
    only collect caliper.log & report.html once after a test.
    :return: 1
    """
    shutil.copyfile("./report.html", "./caliper_history/report/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S") + " report.html")
    shutil.copyfile("./caliper.log", "./caliper_history/log/" + test_datetime.strftime("%Y-%m-%d %H:%M:%S") + " caliper.log")
    return 1


def test_once():
    clean()
    check()
    gen_nodes()
    ch_group_config()
    ch_node_config()
    gen_docker_scripts()
    copy_nodes_to_all_host()
    gen_network_config()
    gen_benchmark_config()
    test_datetime, get_result, set_result = test()
    caliper_history(test_datetime)


if __name__ == '__main__':
    clean()
