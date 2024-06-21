import json
import logging
import os
import time
import ipaddress
import asyncio
from datetime import timedelta
import requests
from geoip2.database import Reader
from geoip2.errors import AddressNotFoundError
from tqdm.asyncio import tqdm

from stx_node_map.util import file_write, assert_env_vars

logging.basicConfig(level=logging.INFO)

this_dir = os.path.abspath(os.path.dirname(__file__))

# Global dictionary to track neighbors keyed by public key hash
global_neighbors = {}

def make_core_api_url(host: str):
    if "hiro" in host:
        return "http://{}/v2/neighbors".format(host)
    return "http://{}:20443/v2/neighbors".format(host)

async def get_neighbors(host: str):
    url = make_core_api_url(host)
    try:
        response = await asyncio.to_thread(requests.get, url, timeout=(2,15))
        response.raise_for_status()
        json = response.json()
    except Exception as e:
        # logging.error(f"Error fetching neighbors from {host}: {e}")
        return host, []

    all_ = [{"public_key_hash": x["public_key_hash"], "ip": x["ip"]} for x in json.get("sample", [])] + \
           [{"public_key_hash": x["public_key_hash"], "ip": x["ip"]} for x in json.get("inbound", [])] + \
           [{"public_key_hash": x["public_key_hash"], "ip": x["ip"]} for x in json.get("outbound", [])]

    unique = list({v['public_key_hash']: v for v in all_}.values())
    return host, [a for a in unique if a["ip"] != "0.0.0.0"]

async def scan_list(list_, scanned):
    tasks = []
    pbar = tqdm(total=len(list_), desc="Scanning neighbors")
    found = []

    for node in list_:
        if node["public_key_hash"] in scanned:
            logging.debug(f"Skipping {node['ip']} - already scanned.")
            node["neighbors"] = global_neighbors.get(node["public_key_hash"], [])
            found.append(node)
            pbar.update()
            continue
        if ipaddress.ip_address(node["ip"]).is_private:
            logging.debug(f"Skipping {node['ip']} - private IP.")
            node["neighbors"] = []
            found.append(node)
            pbar.update()
            continue

        task = asyncio.create_task(get_neighbors(node["ip"]))
        tasks.append(task)
        logging.debug(f"Created task for {node['ip']} with task {task}")

    start_time = time.time()
    for future in asyncio.as_completed(tasks):
        host, result = await future
        node = next((n for n in list_ if n["ip"] == host), None)
        if node:
            if result:
                logging.debug(f"Neighbors found for {node['ip']}: {result}")
            else:
                logging.debug(f"No neighbors found for {node['ip']}")

            node["neighbors"] = [n["ip"] for n in result] if result else []
            global_neighbors[node["public_key_hash"]] = node["neighbors"]
            if node["public_key_hash"] not in [x["public_key_hash"] for x in found]:
                found.append(node)
            for n in result:
                if n["public_key_hash"] not in [x["public_key_hash"] for x in found]:
                    found.append(n)
        else:
            logging.warning(f"No matching node found for task with host {host}")
        pbar.update()

    pbar.close()
    end_time = time.time()
    elapsed_time = timedelta(seconds=end_time - start_time)
    logging.info(f"Scanning took {elapsed_time}")
    found = [node for node in found if node["public_key_hash"] not in scanned]
    found = list({v['public_key_hash']: v for v in found}.values())
    logging.info(f"new neighbor nodes found: {len(found)}")

    return found

async def worker():
    scanned = set()
    _, seed = await get_neighbors(assert_env_vars("DISCOVERER_MAIN_NODE"))
    if len(seed) == 0:
        return

    logging.info(f"{len(seed)} found / {len(scanned)} scanned")
    # scan
    found = await scan_list(seed, scanned)
    scanned.update([node["public_key_hash"] for node in seed])
    logging.info(f"{len(found)} found / {len(scanned)} scanned")
    found += await scan_list(found, scanned)
    scanned.update([node["public_key_hash"] for node in found])
    logging.info(f"{len(found)} found / {len(scanned)} scanned")
    found += await scan_list(found, scanned)
    scanned.update([node["public_key_hash"] for node in found])
    logging.info(f"{len(found)} found / {len(scanned)} scanned")

    # make list unique
    found = list({v['public_key_hash']: v for v in found}.values())

    logging.info("Total {} nodes found.".format(len(found)))
    logging.info("Detecting locations")

    result = []

    reader = Reader(os.path.join(this_dir, "..", "..", "..", 'GeoLite2-City.mmdb'))
    
    for node in found:
        geo = None
        try:
            geo = reader.city(node["ip"])
        except AddressNotFoundError:
            # The IP address was not found in the database
            pass

        if geo is not None:
            # logging.info("{} is a public node".format(node["ip"]))
            # neighbors = await get_neighbors(node["ip"])
            item = {
                "public_key_hash": node["public_key_hash"],
                "address": node["ip"],
                "neighbors": global_neighbors.get(node["public_key_hash"], []),
                "location": {
                    "lat": geo.location.latitude,
                    "lng": geo.location.longitude,
                    "country": geo.country.iso_code,
                    "city": geo.city.name
                }
            }
        else:
            # logging.info("{} is a private node".format(node["ip"]))

            item = {
                "public_key_hash": node["public_key_hash"],
                "address": node["ip"]
            }

        result.append(item)

    save_path = os.path.join(this_dir, "..", "..", "..", "data.json")
    file_write(save_path, json.dumps(result))
    logging.info(f"Saved at {save_path}")

def main():
    try:
        while True:
            loop = asyncio.get_event_loop()
            start_time = time.time()
            loop.run_until_complete(worker())
            end_time = time.time()            
            elapsed_time = timedelta(seconds=end_time - start_time)
            logging.info("Discovery took {}".format(elapsed_time))
            time.sleep(120)
    except KeyboardInterrupt:
        print("Exiting script...")