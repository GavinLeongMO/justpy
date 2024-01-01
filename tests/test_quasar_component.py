from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import unittest
import os.path
import os
from tests.browser_test import SeleniumBrowsers

class QuasarComponentTest(unittest.TestCase):
    def test_style(self):
        drv=SeleniumBrowsers(headless=False).getFirst()
        cwd=os.getcwd()
        drv.get(os.path.join(cwd,"tests","quasar_component_test_page.html"))
        drv.find_element(By.XPATH ,"//div[text()='test']")
        drv.close()
