import boto3
import re
import pandas as pd
import os
import numpy as np
import math
import config
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import random
import traceback
from time import sleep

from threading import Thread

import emails

import csv
import json

import requests

from datetime import datetime as dt

import warnings


def send_plain_email(subject, text):
    ses_client = boto3.client("ses", region_name="us-east-2")
    CHARSET = "UTF-8"

    response = ses_client.send_email(
        Destination={
            "ToAddresses": [
                config.email_to,
            ],
        },
        Message={
            "Body": {
                "Text": {
                    "Charset": CHARSET,
                    "Data": text,
                }
            },
            "Subject": {
                "Charset": CHARSET,
                "Data": subject,
            },
        },
        Source=config.email_from,
    )

    print(response)


def get_price_from_distributor_items(lst):
    prices = []
    for elt in lst:
        price = elt['price']
        if price:
            prices.append(float(price.replace('$', '').replace(',', '')))
    if prices:
        distributor_items_price = np.min(prices)
        return distributor_items_price
    else:
        print("No distributed price found")
        return


def pad_upc(upc):
    upc = str(upc)
    if len(upc) == 12:
        return "'" + upc + "'"
    elif len(upc) < 12:
        pad_n = 12 - len(upc)
        upc = '0' * pad_n + upc
        return "'" + upc + "'"
    else:
        # print("upc has len : ", len(upc))
        return "'" + upc + "'"


def log_to_file(string):
    print(string)
    with open("tmp/logs.txt", "a") as f:
        f.write(string + '/n')


def init_driver(is_proxy=False, proxy=None, proxy_server=None):
    """
    initiate the undetected chrome driver
    """
    # intitate the driver instance with options and chrome version
    attempt = 0
    done = False
    driver = None

    while not done and attempt < 4:
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        #options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if config.use_proxy:
            proxy_servers = config.proxies
            if proxy_servers and len(proxy_servers):
                proxy_server = random.choice(proxy_servers)
                print("using proxy_server : ", proxy_server)
                options.add_argument(f"--proxy-server={proxy_server}")
        try:  # will patch to newest Chrome driver version
            driver = uc.Chrome(use_subprocess=True, options=options,
                               executable_path=config.driver_executable_path)#, driver_executable_path)
            done = True
        except:  # newest driver version not matching Chrome version
            err = traceback.format_exc()
            print("ERR initiating driver: ", err)
            attempt += 1

    return driver


def load_ucps(ucp_csv_path):
    """
    yield each value of upcs and prices from saved API data (generator)
    """
    print("Loading upcs...")
    s3 = boto3.client('s3')
    s3.download_file(config.BUCKET_NAME, 'prices/' + ucp_csv_path.split('/')[-1], ucp_csv_path)
    df = pd.read_csv(ucp_csv_path)
    upcs = df.upc.values.tolist()
    prices = df.price.values.tolist()
    target_prices = df.target_price.values.tolist()
    price_difference_percents = df.price_difference_percent.values.tolist()
    price_difference_amounts = df.price_difference_amount.values.tolist()
    product_types = df.product_type.values.tolist()

    for upc, price, target_price, price_difference_percent, price_difference_amount, product_type in zip(
            upcs, prices, target_prices, price_difference_percents, price_difference_amounts, product_types):
        if (math.isnan(target_price) or
                math.isnan(price_difference_percent) or
                math.isnan(price_difference_amount)):
            yield upc, price, product_type


def remove_duplicates(ucp, upcs_products):
    if len(upcs_products) > 0:
        new_lst = [t for t in tuple((set(tuple(i) for i in upcs_products)))]
        print(
            f"{len(upcs_products) - len(new_lst)} duplicated products removed from {len(upcs_products)} "
            f"products for ucp {ucp}.")
    else:
        log_to_file(f"upcs_products is empty. 0 products scraped from the 3 websites for upc {ucp}")
        new_lst = []

    return new_lst
