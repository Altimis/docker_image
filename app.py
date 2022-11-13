import boto3
from botocore.client import ClientError
import logging
from os.path import expanduser
import re
import pandas as pd
import os
from utils import send_plain_email
import glob
import numpy as np
import math
import config
from utils import get_price_from_distributor_items, pad_upc, \
    log_to_file, init_driver, load_ucps, remove_duplicates
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import random
import traceback
from time import sleep
from tabulate import tabulate
from threading import Thread

from pyvirtualdisplay import Display

import csv
import json

import requests

from datetime import datetime as dt

import warnings

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(message)s')



# from waitress import serve


##########
# config #
##########

user_agent = config.user_agent
token = config.token
api_url = config.url
username = config.username
password = config.password

# call s3 bucket
bucket = boto3.resource('s3').Bucket(config.BUCKET_NAME)
s3 = boto3.client('s3')

class Scraper:
    def __init__(self, barcodelookup_url, gunengine_url, gundeals_url, wikiarms_url):
        self.upcs_products = []
        print("Setting up the main class")
        self.barcodelookup_url = barcodelookup_url
        self.gunengine_url = gunengine_url
        self.gundeals_url = gundeals_url
        self.wikiarms_url = wikiarms_url
        # print("self.gundeals url : ", self.gundeals_url)
        self.failed = False

    # pad the upc with 0s

    # main function that sends data to the cloud via API
    def get_items(self):
        # read the file
        try:
            s3.download_file(config.BUCKET_NAME, 'utils/timestamps.txt', expanduser("~") +
                             '/docker_image/'+'tmp/timestamps.txt')
            log_to_file(f"timestamps found in s3")
        except:
            open(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'w').close()
            log_to_file(f"timestamps not found in s3")

        os.chmod(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 0o777)

        with open(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'r') as f:
            lines = f.readlines()
            lines = [line.rstrip() for line in lines if line]

        if lines:
            timestamps = [dt.strptime(line, '%Y-%m-%d_%H-%M-%S') for line in lines]
            latest_timestamp = max(timestamps)
            log_to_file(f"number of saved timestamps : {len([timestamp.strftime('%Y-%m-%d_%H-%M-%S') for timestamp in timestamps])}")
            log_to_file(f"Latest csv : {latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}")
            latest_df_name = f"prices/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
            s3.download_file(config.BUCKET_NAME, latest_df_name,
                             expanduser("~") + '/docker_image/'+f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv")
            os.chmod(expanduser("~") + '/docker_image/'+f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv", 0o777)
            log_to_file(f'Latest df downloaded : {latest_df_name}')
            latest_df = pd.read_csv(expanduser("~") + '/docker_image/'+f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv")
            target_prices = latest_df.target_price.values.tolist()
            price_difference_percents = latest_df.price_difference_percent.values.tolist()
            price_difference_amounts = latest_df.price_difference_amount.values.tolist()
            is_completed = all(
                (not math.isnan(el1) or not math.isnan(el2) or not math.isnan(el3)) for el1, el2, el3 in zip(
                    target_prices, price_difference_percents, price_difference_amounts))
            nothing = False
        else:
            nothing = True
            is_completed = True

        if is_completed:
            if nothing:
                log_to_file("This is the first scraping session. First csv will be created.")
            else:
                #warning_upcs = latest_df[np.abs(latest_df['price_difference_percent']) > config.threshold][
                #    'upc'].values.tolist()
                #log_to_file(f"Warning for these UPCs : {warning_upcs}")
                #print("Completed.")
                log_to_file("All csvs are completed. Creating a new scraping session.")
            now = dt.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.ucp_csv_path = expanduser("~") + '/docker_image/'+f"tmp/results_{now}.csv"
        else:
            self.ucp_csv_path = expanduser("~") + '/docker_image/'+\
                                f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
            log_to_file(f"The file results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv "
                        f"is not completed. Resuming scraping.")
            return

        to_return = []
        log_to_file(f"Getting data from API ...")
        try:
            i = 1
            total = 1
            j = 0
            while i <= total:
                params = {
                    "page": i
                }
                # print("current page : ", i)
                # get the response
                response = requests.get(api_url, auth=(username, password), params=params)
                # retrieve data from the response json
                if int(response.status_code) == 200:
                    for elt in response.json()['results']:
                        row = {}
                        # upc
                        upc = pad_upc(elt['upc'])
                        if upc:
                            # print("UPC : ", upc)
                            # if upc != "'723189045227'":
                            #    continue
                            row['upc'] = upc
                        else:
                            row['upc'] = None
                        # price
                        price = float(elt['price'].replace('$', '').replace(',', ''))
                        if price:
                            # print("Price : ", price)
                            row['price'] = price
                        else:
                            row['price'] = None
                        # distributor price
                        distributor_items_price = get_price_from_distributor_items(elt['distributor_items'])
                        row['distributor_items_price'] = distributor_items_price
                        # print("distributor_items_price : ", distributor_items_price)
                        # category name
                        category_name = elt['category_name']
                        row['category_name'] = category_name
                        product_type = elt['product_type']
                        row['product_type'] = product_type
                        # print("category name : ", category_name)
                        to_return.append(row)
                        if j % 100 == 0:
                            j += 1
                            log_to_file(f"Got {j} items from the API")
                    total = int(response.json()['pages'])
                    # print("pages left : ", total - i)
                    i += 1
                    # print("items pulled : ", len(to_return))

                    df = pd.DataFrame.from_dict(to_return)

                    df['target_price'] = ''
                    df['price_difference_percent'] = ''
                    df['price_difference_amount'] = ''
                    df['price_min'] = ''
                    df['price_max'] = ''

                    # df = df.sample(frac=0.5)

                    # print(self.ucp_csv_path)

                    df.to_csv(self.ucp_csv_path, index=False)

                    with open(self.ucp_csv_path, 'r') as infile:
                        reader = list(csv.reader(infile))
                        reader = reader[::-1]  # the date is ascending order in file
                        # reader.insert(0,lists)

                    with open(self.ucp_csv_path, 'w', newline='') as outfile:
                        writer = csv.writer(outfile)
                        for line in reversed(reader):  # reverse order
                            writer.writerow(line)
                    # upload file from tmp to s3 key
                    try:
                        bucket.upload_file(self.ucp_csv_path, 'prices/' + self.ucp_csv_path.split('/')[-1])
                    except:
                        log_to_file("Couldn't upload csv")

                else:
                    log_to_file(f'Error getting data' + str(response.json()))

            # write the time to file
            with open(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'a') as file:
                file.write(now + '\n')
            try:
                bucket.upload_file(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'utils/timestamps.txt')
            except:
                log_to_file("Couldn't upload timestamps.txt")
            log_to_file("Uploaded timestamps file to S3")

        except Exception as e:
            print(e)

        return len(df)

    def scrape_wikiarms(self, ucp, product_type):
        """
        scrape barcodelookup websites
        """
        # iterate through all ucps
        # for ucp in self.ucps:
        scraper_name = 'wikiarms'
        cat_names = {
            'guns': ['Handgun', 'Long Gun'],
            'ammo': ['Ammunition'],
            'parts': ['Suppressor', 'Merchandise']
        }
        ucp = ucp.replace("'", "")
        stores_prices = []
        f = False
        for key, value in cat_names.items():
            if product_type in value:
                cat_name = key
                f = True
                break
        if not f:
            cat_name = 'guns'
        # intiate the driver
        driver = init_driver()
        if not driver:
            log_to_file(f"[{scraper_name}] there was a fatal problem with the chromedriver intialization!")
            self.failed = True
            return
        # get the url
        url = self.wikiarms_url + cat_name + '?q=' + str(ucp)
        log_to_file(f"[{scraper_name}] Getting products with UCP : {ucp} : {url}")
        try:
            driver.get(url)
        except:
            err = ""  # traceback.format_exc()
            log_to_file(f"[{scraper_name}] There was an issue getting the url : {url}"
                        f"\nError Traceback: {err}")
            driver.close()
            return
        # sleep(random.uniform(, 6))

        # self.log_to_file(f"page source : {driver.page_source}")

        # get products elements
        try:
            els = driver.find_elements(By.XPATH, "//div[@id='products-table']/table/tbody/tr")
        except Exception:
            err = ""  # traceback.format_exc()
            log_to_file(f"[{scraper_name}] There was an issue pulling [all products] with the ucp {ucp}"
                        f"\nError Traceback: ")
            driver.close()
            return
        log_to_file(f"[{scraper_name}] got {len(els)} elements")
        # iterate through all shops
        stores_prices = []
        for j, el in enumerate(els):
            # print(f"[{scraper_name}] getting element {j}")
            # get the price and store elements
            try:
                stroe_name = el.find_elements(By.XPATH, "./td")[-1].text.lower().rstrip().lstrip()
                price = el.find_element(By.XPATH, './td[2]').text
                if price != "MAP":
                    price = float(price.replace('$', '').replace(',', ''))
                else:
                    continue

            except Exception as e:
                err = traceback.format_exc()
                log_to_file(f"[{scraper_name}] There was an issue pulling [a product] with the ucp {ucp}"
                            f"\nError Traceback:")
                continue
            # self.log_to_file(f"price : {price}, store_url : {store_url}")
            stores_prices.append((stroe_name, price))

        # close the driver
        driver.close()
        log_to_file(f"[{scraper_name}] got the prices : {stores_prices}")
        # save products for this ucp
        self.upcs_products += stores_prices
        log_to_file(f"[{scraper_name}] Finished scraping with {len(stores_prices)} items.")

    def scrape_gunengine(self, ucp, product_type):
        scraper_name = 'gunengine'
        log_to_file(f"Scraping {upc} with {scraper_name} started")
        cat_names = {
            'guns': ['Handgun', 'Long Gun'],
            'ammo': ['Ammunition'],
            'parts': ['Suppressor', 'Merchandise']
        }
        ucp = ucp.replace("'", "")
        stores_prices = []
        f = False
        for key, value in cat_names.items():
            if product_type in value:
                cat_name = key
                f = True
                break
        if not f:
            cat_name = 'guns'
        driver = init_driver()
        if not driver:
            log_to_file(f"[{scraper_name}] there was a fatal problem with the chromedriver intialization!")
            self.failed = True
            return
        # get the url
        url = self.gunengine_url + cat_name + '?q=' + str(ucp)
        log_to_file(f"[{scraper_name}] Getting products with UCP : {ucp} : {url} for category {cat_name}")
        try:
            driver.get(url)
        except:
            err = traceback.format_exc()
            log_to_file(f"[{scraper_name}] There was an issue getting the url : {url}")
            driver.close()
            return
        sleep(random.uniform(0.5, 1))

        # get products elements
        try:
            found = driver.find_element(By.XPATH, '//*[@id="main-content"]/div[2]/p').text
        except:
            sleep(random.uniform(1, 2))
            found = driver.find_element(By.XPATH, '//*[@id="main-content"]/div[2]/p').text

        # continue if 0 products found
        if found:
            if int(re.search(r'\d+', found).group()) == 0:
                log_to_file(f"[{scraper_name}] 0 results found for ucp : {ucp}")
                driver.close()
                return
        else:
            log_to_file(f"[{scraper_name}] 0 results found for ucp : {ucp}")
            driver.close()
            return

        # show all stores
        try:
            driver.find_element(By.XPATH, f'//*[@id="upc{ucp}"]/a').click()
        except Exception as e:
            log_to_file(f"[{scraper_name}] Couldn't get all results for UPC {ucp}")

        sleep(random.uniform(0.5, 1))
        # get stores elements
        try:
            variant_els = driver.find_elements(By.XPATH, "//div[@class='variant']")
        except Exception as e:
            err = traceback.format_exc()
            log_to_file(f"[{scraper_name}] There was an issue pulling [all products] with the ucp {ucp}")
            driver.close()
            return
        # iterate through all shops
        stores_prices = []
        for j, variant_el in enumerate(variant_els):
            # print(f"[{scraper_name}] getting element {j}")
            # get the price and store elements
            try:
                price = float(variant_el.find_element(
                    By.XPATH, "./div[1]/a[1]/span[@class='variant-price ']").text.replace('$', '').replace(',', ''))
                store_name = variant_el.find_element(
                    By.XPATH, "./div[1]/a[1]/span[@class='variant-store']").text.lower().rstrip().lstrip()
            except Exception as e:
                err = traceback.format_exc()
                log_to_file(f"[{scraper_name}] There was an issue pulling [a product] with the ucp {ucp}")
                continue
            # self.log_to_file(f"price : {price}, store_url : {store_url}")
            stores_prices.append((store_name, price))

        # close the driver
        driver.close()
        log_to_file(f"[{scraper_name}] got the prices : {stores_prices}")
        # save productsUnnamed: 0 for this ucp
        self.upcs_products += stores_prices
        log_to_file(f"[{scraper_name}] Finished scraping with {len(stores_prices)} items.")

    def scrape_gundeals(self, ucp):
        """
        scrape barcodelookup websites
        """
        # iterate through all ucps
        scraper_name = 'gundeals'
        log_to_file(f"Scraping {upc} with {scraper_name} started")
        ucp = ucp.replace("'", "")
        stores_prices = []
        # intiate the driver
        driver = init_driver()
        if not driver:
            log_to_file(f"[{scraper_name}] there was a fatal problem with the chromedriver intialization!")
            self.failed = True
            return
        # get the url
        url = self.gundeals_url + str(ucp)
        log_to_file(f"[{scraper_name}] Getting products with UCP : {ucp} : {url}")
        try:
            driver.get(url)
        except:
            err = traceback.format_exc()
            log_to_file(f"There was an issue getting the url : {url}"
                        f"\nError Traceback: {err}")
            driver.close()
            return
        sleep(random.uniform(1, 2))

        # print(driver.page_source)

        # get products elements
        try:
            els = driver.find_elements(By.XPATH, "//table[@id='price-compare-table']/tbody/tr")
        except Exception as e:
            err = traceback.format_exc()
            log_to_file(f"There was an issue pulling [all products] with the ucp {ucp} from [gundeals] website.")
            driver.close()
            return

        # iterate through all shops
        stores_prices = []
        log_to_file(f"[{scraper_name}] got {len(els)} elements")
        for j, el in enumerate(els):
            # print(f"[{scraper_name}] getting element {j}")
            # get the price and store elements
            if 'out of stock' in el.text.lower():
                log_to_file(f"[{scraper_name}] out of stock found")
                break
            try:
                price = el.get_attribute('data-price')
                price = float(price.replace('$', '').replace(',', ''))
                store_name = el.find_element(By.XPATH, './/td[1]/div[1]/a[1]/span').text.lower().rstrip().lstrip()
            except Exception as e:
                err = traceback.format_exc()
                log_to_file(f"There was an issue pulling [a product] with the ucp {ucp} from [gundeals] website.")
                continue
            # if j % 10 == 0:
                # print("inserting element ", j)
            stores_prices.append((store_name, price))

        # close the driver
        driver.close()
        # break
        log_to_file(f"[{scraper_name}] got the prices : {stores_prices}")
        # save products for this ucp
        self.upcs_products += stores_prices
        log_to_file(f"[{scraper_name}] Finished scraping with {len(stores_prices)} items.")

    def scrape_barcodelookup(self, ucp):
        """
        scrape barcodelookup websites
        """
        # iterate through all ucps
        scraper_name = 'barcodelookup'
        log_to_file(f"Scraping {upc} with {scraper_name} started")
        ucp = ucp.replace("'", "")
        # intiate the driver
        driver = init_driver()
        if not driver:
            log_to_file(f"[{scraper_name}] there was a fatal problem with the chromedriver initialization!")
            self.failed = True
            return
        # get the url
        url = self.barcodelookup_url + str(ucp)
        log_to_file(f"[{scraper_name}] Getting products with UCP : {ucp} : {url}")
        try:
            driver.get(url)
        except:
            err = traceback.format_exc()
            log_to_file(f"There was an issue getting the url : {url}")
            driver.close()
            return
        sleep(random.uniform(1, 2))

        # get products elements
        try:
            els = driver.find_elements(By.XPATH, "//div[@class='store-list']/ol/li")
        except Exception as e:
            err = traceback.format_exc()
            log_to_file(f"There was an issue pulling [all products] with the ucp {ucp} from [gundeals] website.")
            driver.close()
            return

        # iterate through all shops
        stores_prices = []
        print(f"got {len(els)} elements for {scraper_name}")
        for j, el in enumerate(els):
            # get the price and store elements
            try:
                price = el.find_element(By.XPATH, ".//span[2]")
                price = float(price.replace('$', '').replace(',', ''))
                store_name = el.find_element(By.XPATH, './/span[1]').text.lower().rstrip().lstrip()
            except Exception as e:
                err = traceback.format_exc()
                log_to_file(f"There was an issue pulling [a product] with the ucp {ucp} from [{scraper_name}] website.")
                continue
            stores_prices.append((store_name, price))

        # close the driver
        driver.close()
        # break
        log_to_file(f"[{scraper_name}] got the prices : {stores_prices}")
        # save products for this ucp
        self.upcs_products += stores_prices
        log_to_file(f"[{scraper_name}] Finished scraping with {len(stores_prices)} items.")

    def scrape_all(self):
        """

        """
        # yielding upcsself.ucp_csv_path
        #s3 = boto3.client('s3')
        log_to_file("getting upcs and prices from the API ...")
        len_items = self.get_items()
        if len_items:
            log_to_file(f"Got {len_items}")
        else:
            log_to_file("an uncompleted csv file already exists")

        upcs_prices_generator = load_ucps(self.ucp_csv_path)

        json_upcs_products = {}

        for upc, price, product_type in upcs_prices_generator:
            #if upc != "'792695234166'":
            #    continue
            log_to_file(f"scraping for upc {upc} and price {price} ...")
            self.upcs_products = []
            # Scraping starts
            log_to_file("Scraping 3 websites started")
            # self.scrape_gundeals(ucp = upc)
            try:
                """
                t1 = Thread(target=self.scrape_gundeals, args=(upc,))
                t2 = Thread(target=self.scrape_gunengine, args=(upc, product_type))
                t3 = Thread(target=self.scrape_wikiarms, args=(upc, product_type))
                #t4 = Thread(target=self.scrape_barcodelookup, args=(upc,))
                t1.start()
                t2.start()
                t3.start()
                #t4.start()
                t1.join()
                t2.join()
                t3.join()
                #t4.join()
                """

                self.scrape_gundeals(upc)
                self.scrape_gunengine(upc, product_type)
                self.scrape_wikiarms(upc, product_type)

                # self.scrape_barcodelookup(upc)
                ###
                # self.scrape_wikiarms(upc, product_type)
                # self.scrape_gundeals(upc)
                # self.scrape_gunengine(upc, product_type)
                ###

                #log_to_file("Scraping 3 websites finished")
                log_to_file("Checking duplicates")
                upcs_products = remove_duplicates(upc, self.upcs_products)

                json_upcs_products[upc.replace("'", '')] = [l for l in upcs_products]

                with open(expanduser("~") + '/docker_image/'+f"tmp/json_upcs_prices_{self.ucp_csv_path.split('/')[-1].split('.')[0]}.json",
                          'w') as outfile:
                    json.dump(json_upcs_products, outfile)
                try:
                    bucket.upload_file(expanduser("~") + '/docker_image/'+f"tmp/json_upcs_prices_{self.ucp_csv_path.split('/')[-1].split('.')[0]}.json",
                                   f"prices/json_upcs_prices_{self.ucp_csv_path.split('/')[-1].split('.')[0]}.json")
                except:
                    log_to_file("Couldn't upload json")

                # print("len : ", len(upcs_products))
                if len(upcs_products) != 0:
                    scraped_prices = list(zip(*upcs_products))[-1]
                    scraped_prices = np.array(scraped_prices, dtype=np.float64)
                    target = np.abs(np.min([np.mean(scraped_prices), np.median(scraped_prices)]))
                    diff_perc = np.abs(round(target / float(price) - 1, 3))
                    diff_amount = np.abs(price - target)
                    price_min = np.min(scraped_prices)
                    price_max = np.max(scraped_prices)
                elif not self.failed:
                    log_to_file(
                        f"Target price and difference price will be inserted as N/A. No prices were scraped.")
                    scraped_prices = []
                    target = 'N/A'
                    diff_perc = 'N/A'
                    diff_amount = 'N/A'
                    price_min = 'N/A'
                    price_max = 'N/A'
                else:
                    log_to_file(
                        f"There was a fatal issue initiating one of the driver. Nothing will be inserted for upc {upc} and scraping will be resumed for another session.")
                    continue
                #s3 = boto3.client('s3')
                s3.download_file(config.BUCKET_NAME, 'prices/' + self.ucp_csv_path.split('/')[-1],
                                 self.ucp_csv_path)

                with open(self.ucp_csv_path) as inf:
                    reader = csv.reader(inf.readlines())

                with open(self.ucp_csv_path, 'w') as f:
                    writer = csv.writer(f)
                    for i, line in enumerate(reader):
                        # print(line)
                        if i == 0:
                            writer.writerow(line)
                            continue
                        if line[0] == upc:
                            log_to_file(f"Target price : {target} inserted for the price {price}")
                            if target != 'N/A':
                                line[5] = round(target, 3)
                                line[6] = diff_perc
                                line[7] = round(diff_amount, 3)
                                try:
                                    line[8] = round(price_min, 2)
                                    line[9] = round(price_max, 2)
                                except:
                                    pass
                            else:
                                line[5] = target
                                line[6] = diff_perc
                                line[7] = diff_amount
                                try:
                                    line[8] = price_min
                                    line[9] = price_max
                                except:
                                    pass
                            writer.writerow(line)
                        else:
                            writer.writerow(line)
                    writer.writerows(reader)
                try:
                    bucket.upload_file(self.ucp_csv_path, 'prices/' + self.ucp_csv_path.split('/')[-1])
                except:
                    log_to_file("Couldn't upload csv")
                log_to_file(
                    f"Finished processing upc {upc} with target price : {target} and difference percentage : {diff_perc}")

            except:
                er = traceback.format_exc()
                log_to_file("A major problem occured in one of the scrapers : " + str(er))
                # print("A major problem occured in one of the scrapers : " + str(e))
            try:
                bucket.upload_file(expanduser("~") + '/docker_image/'+"tmp/logs.txt", "logs/logs.txt")
            except:
                log_to_file("Couldn't upload logs")
            #with open(expanduser("~") + '/docker_image/tmp/'+upc+'.txt', 'w') as f:
            #    f.write(upc)

        #############################

        try:
            s3.download_file(config.BUCKET_NAME, 'utils/timestamps.txt', expanduser("~") + '/docker_image/'+'tmp/timestamps.txt')
        except:
            open(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'w').close()

        os.chmod(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 0o777)

        with open(expanduser("~") + '/docker_image/'+'tmp/timestamps.txt', 'r') as f:
            lines = f.readline()
            lines = lines.split('\n')
            lines = [line.rstrip() for line in lines if line]

        if lines:
            timestamps = [dt.strptime(line, '%Y-%m-%d_%H-%M-%S') for line in lines]
            latest_timestamp = max(timestamps)
            print("latest csv : ", latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S'))
            s3.download_file(config.BUCKET_NAME, f"prices/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv",
                             expanduser("~") + '/docker_image/'+f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv")
            latest_df = pd.read_csv(expanduser("~") + '/docker_image/'+f"tmp/results_{latest_timestamp.strftime('%Y-%m-%d_%H-%M-%S')}.csv")
            target_prices = latest_df.target_price.values.tolist()
            # print("target price : ", target_prices)
            price_difference_percents = latest_df.price_difference_percent.values.tolist()
            price_difference_amounts = latest_df.price_difference_amount.values.tolist()
            is_completed = all(
                (not math.isnan(el1) or not math.isnan(el2) or not math.isnan(el3)) for el1, el2, el3 in zip(
                    target_prices, price_difference_percents, price_difference_amounts))
        else:
            is_completed = True

        #####################

        if is_completed:
            log_to_file("Session completed")
        try:
            bucket.upload_file(expanduser("~") + '/docker_image/'+"tmp/logs.txt", "logs/logs.txt")
        except:
            log_to_file("Couldn't upload logs")
        # Send warning
        s3.download_file(config.BUCKET_NAME, 'prices/' + self.ucp_csv_path.split('/')[-1],
                         self.ucp_csv_path)
        df_f = pd.read_csv(self.ucp_csv_path)
        df_warning = df_f[df_f['price_difference_percent'] > config.threshold]
        len_df_warning = len(df_warning)
        warning_df_name = self.ucp_csv_path.split('/')[-1].replace('results', 'warning')

        if len_df_warning > 0:
            df_warning_to_save = df_warning[['upc', 'price_difference_percent', 'price', 'target_price']]
            df_warning_to_save.to_csv(expanduser("~") + '/docker_image/'+f"tmp/{warning_df_name}")
            try:
                bucket.upload_file(expanduser("~") + '/docker_image/'+f"tmp/{warning_df_name}",
                                   f"reports/{warning_df_name}")
            except:
                log_to_file("Couldn't upload report")
            warning_text = f"There are {len_df_warning} items " \
                           f"that have a price difference bigger than {config.threshold}.\n " \
                           f"Report can be found in file named {warning_df_name} under reports directory (in S3)."
            #print("Email sent : ", warning_text)
        else:
            warning_text = f"There are 0 items " \
                           f"that have a price difference bigger than {config.threshold}."
            #print("Email sent : ", warning_text)
        if is_completed:
            #send_plain_email(subject=subject, text=warning_text)
            log_to_file(f"Warning sent : {warning_text}")


def main():
    try:
        s3.download_file(config.BUCKET_NAME, 'logs/logs.txt', expanduser("~") + '/docker_image/'+'tmp/logs.txt')
        f = open(expanduser("~") + '/docker_image/' + "tmp/logs.txt", "w")
        f.write("first\n")
        f.close()
        try:
            bucket.upload_file(expanduser("~") + '/docker_image/'+'tmp/logs.txt', 'logs/logs.txt')
        except:
            log_to_file("Couldn't upload logs")
    except Exception as e:
        print(e)
        f = open(expanduser("~") + '/docker_image/'+"tmp/logs.txt", "w")
        f.write("first\n")
        f.close()
    try:
        scraper = Scraper(barcodelookup_url=config.barcodelookup_url, gunengine_url=config.gunengine_url,
                          gundeals_url=config.gundeals_url, wikiarms_url=config.wikiarms_url)
        log_to_file("Scraper started")
        scraper.scrape_all()

    except Exception as e:
        log_to_file(f"Execution failed: {e}")


if __name__ == "__main__":
    # remove all files in tmp dir

    display = Display(visible=0, size=(1024, 768))
    display.start()

    print("Code started")
    print("Emptying tmp dir")

    files = glob.glob(expanduser("~") + '/docker_image/'+'tmp/*')
    for f in files:
        try:
            #continue
            os.remove(f)
        except:
            continue

    try:
        print(f"Checking if bucket exists...")
        boto3.resource('s3').meta.client.head_bucket(Bucket=config.BUCKET_NAME)
    except ClientError:
        print(f"Bucket {config.BUCKET_NAME} doesn't exist. Creating it..")
        s3.create_bucket(Bucket=config.BUCKET_NAME)
    main()
