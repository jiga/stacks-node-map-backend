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

from stx_node_map.util import file_write, assert_env_vars

logging.basicConfig(level=logging.INFO)

this_dir = os.path.abspath(os.path.dirname(__file__))


def make_core_api_url(host: str):
    if "hiro" in host:
        return "http://{}/v2/neighbors".format(host)

    return "http://{}:20443/v2/neighbors".format(host)


async def get_neighbors(host: str):
    url = make_core_api_url(host)
    try:
        json = requests.get(url, timeout=1).json()
    except BaseException:
        return []

    # collect all ip addresses
    all_ = [x["ip"] for x in json["sample"]] + [x["ip"] for x in json["inbound"]] + [x["ip"] for x in json["outbound"]]

    # make the list unique
    unique = list(set(all_))

    # skip local address
    return [a for a in unique if a != "0.0.0.0"]


async def scan_list(list_, scanned):
    tasks = []
    for address in list_:
        # Skip if the address is a private address
        if ipaddress.ip_address(address).is_private or address in scanned:
            continue

        logging.info("Scanning {}".format(address))
        tasks.append(get_neighbors(address))

    start_time = time.time()
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    elapsed_time = timedelta(seconds=end_time - start_time)
    logging.info("Scanning took {}".format(elapsed_time))
    
    found = []
    for neighbors in results:
        found += [n for n in neighbors if n not in found]

    return found

async def worker():
    scanned = set()
    seed = await get_neighbors(assert_env_vars("DISCOVERER_MAIN_NODE"))
    print(seed)
    if len(seed) == 0:
        return

    # scan
    found = await scan_list(seed, scanned)
    scanned.update(seed)
    logging.info("{} nodes found.".format(len(set(found))))
    found += await scan_list(list(set(found) - scanned), scanned)
    scanned.update(found)
    logging.info("{} nodes found.".format(len(set(found))))
    found += await scan_list(list(set(found) - scanned), scanned)
    scanned.update(found)
    logging.info("{} nodes found.".format(len(set(found))))

    # make list unique
    found = list(set(found))

    logging.info("{} nodes found.".format(len(found)))
    logging.info("Detecting locations")

    result = []

    reader = Reader(os.path.join(this_dir, "..", "..", "..", 'GeoLite2-City.mmdb'))
    
    for address in found:
        geo = None
        try:
            geo = reader.city(address)
        except AddressNotFoundError:
            # The IP address was not found in the database
            pass

        if geo is not None:
            # logging.info("{} is a public node".format(address))
            neighbors = await get_neighbors(address)
            item = {
                "address": address,
                "neighbors": neighbors,
                "location": {
                    "lat": geo.location.latitude,
                    "lng": geo.location.longitude,
                    "country": geo.country.iso_code,
                    "city": geo.city.name
                }
            }
        else:
            # logging.info("{} is a private node".format(address))

            item = {
                "address": address
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
