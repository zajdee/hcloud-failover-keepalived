#!/usr/bin/env python3
# (c) 2018 Maximilian Siegl

import sys
import json
import os
import requests
import ipaddress
import argparse
from multiprocessing import Process

CONFIG_FILENAME = "config.json"


def get_config_path(config_filename):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), config_filename)


def del_ip(ip_bin_path, ip, interface):
    os.system(ip_bin_path + " addr del " + ip + " dev " + interface)


def add_ip(ip_bin_path, ip, interface):
    os.system(ip_bin_path + " addr add " + ip + " dev " + interface)


def compute_ip(ip, iid):
    iid = iid if iid else "0.0.0.0"
    return ipaddress.ip_network(
        int(ipaddress.ip_network(ip).network_address) + int(ipaddress.ip_address(iid))
    ).compressed


def change_request(
    endstate, url, header, payload, ip_bin_path, floating_ip, floating_ip_iid, interface
):
    if endstate == "BACKUP":
        del_ip(ip_bin_path, compute_ip(floating_ip, floating_ip_iid), interface)
    elif endstate == "FAULT":
        del_ip(ip_bin_path, compute_ip(floating_ip, floating_ip_iid), interface)

    elif endstate == "MASTER":
        add_ip(ip_bin_path, compute_ip(floating_ip, floating_ip_iid), interface)
        print("Post request to: " + url)
        print("Header: " + str(header))
        print("Data: " + str(payload))
        r = requests.post(url, data=payload, headers=header)
        print("Response:")
        print(r.status_code, r.reason)
        print(r.text)
    else:
        print("Error: Endstate not defined!")


def change_aliases(url, header, network_id, alias_ips):
    payload_raw = {"network": network_id, "alias_ips": alias_ips}
    payload = json.dumps(payload_raw)

    print("Post request to: " + url)
    print("Header: " + str(header))
    print("Data: " + str(payload))
    r = requests.post(url, data=payload, headers=header)
    print("Response:")
    print(r.status_code, r.reason)
    print(r.text)


def main(config_filename, arg_endstate):
    with open(get_config_path(config_filename), "r") as config_file:
        config = json.load(config_file)

    header = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + config["api-token"],
    }

    payload_floating_raw = {"server": config["server-id"]}
    payload_floating = json.dumps(payload_floating_raw)

    print("Perform action for transition to " + arg_endstate + " state")

    for ip in config["floating-ips"]:
        url = config["url-floating"].format(ip["floating-ip-id"])
        Process(
            target=change_request,
            args=(
                arg_endstate,
                url,
                header,
                payload_floating,
                config["ip-bin-path"],
                ip["floating-ip"],
                ip.get("floating-ip-iid", None),
                config["interface-wan"],
            ),
        ).start()

    if config["use-private-ips"] == True:
        if arg_endstate == "MASTER":
            for server_id in config["server-ids"]:
                url = config["url-alias"].format(server_id)
                Process(change_aliases(url, header, config["network-id"], []))

            url = config["url-alias"].format(config["server-id"])
            change_aliases(url, header, config["network-id"], config["private-ips"])

            for private_ip in config["private-ips"]:
                add_ip(config["ip-bin-path"], private_ip, config["interface-private"])

        else:
            for private_ip in config["private-ips"]:
                del_ip(config["ip-bin-path"], private_ip, config["interface-private"])


# COMMAND=/opt/hcloud-failover/hcloud_failover.py --config 1.conf INSTANCE LB_1 BACKUP 110
def parse_args():
    parser = argparse.ArgumentParser(
        prog="Hetzner Cloud Failover switcher",
        description="Reroutes the floating IPs to a selected server",
        epilog="Use Python 3 and IPv6.",
    )
    parser.add_argument("--config", default=CONFIG_FILENAME)
    # Four positional arguments added by keepalived
    parser.add_argument("instance")
    parser.add_argument("instance_name")
    parser.add_argument("state")
    parser.add_argument("priority")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = parse_args()
    main(config_filename=args.config, arg_endstate=args.state)
