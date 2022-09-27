import undetected_chromedriver as uc #import undetected_chromedriver as uc #
from fake_useragent import UserAgent
import pyautogui
from selenium import webdriver
import time

clicked = False

hostname = "216.162.209.41"
port = "49155"
proxy_username = "aitjeddiyassine"
proxy_password = "YnYbrgjWgH"
chrome_options = {
    'proxy': {
        'http': f'http://{proxy_username}:{proxy_password}@{hostname}:{port}',
        'https': f'https://{proxy_username}:{proxy_password}@{hostname}:{port}',
        'no_proxy': 'localhost,127.0.0.1'
    }
}


def delete_cache(driver):
    driver.execute_script("window.open('')")  # Create a separate tab than the main one
    driver.switch_to.window(driver.window_handles[-1])  # Switch window to the second tab
    driver.get('chrome://settings/clearBrowserData')  # Open your chrome settings.
    pyautogui.click("clear_data.png")


if __name__ == '__main__':
    ua = UserAgent()
    userAgent = ua.random
    options = webdriver.ChromeOptions()

    #options.add_argument(f'user-agent={userAgent}')
    # options.add_argument('--ignore-certificate-errors-spki-list')
    # # options.add_argument('--ignore-ssl-errors')
    options.add_argument("--disable-infobars")

    browser = uc.Chrome(
        chrome_options=chrome_options,
        options=options,
        use_subprocess=True
    )
    browser.maximize_window()
    browser.get("https://www.myexternalip.com/raw")
    time.sleep(60)
    print(browser.page_source)