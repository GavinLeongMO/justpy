'''
Created on 2022-09-14

@author: wf
'''
import asyncio
from selenium.webdriver.common.by import By
from tests.base_selenium_test import BaseSeleniumTest
from jpcore.webpage import WebPage
import justpy as jp

class TestAjaxWithSelenium(BaseSeleniumTest):
    """
    testing ajax (non-websocket) behavior
    """

    async def asyncSetUp(self):
        await super().asyncSetUp(port=8126)
        
    async def testAjax(self):
        """
        test ajax (non-websocket behavior) according to tutorial
        """
        WebPage.use_websockets=False
        self.browser = await self.getBrowserForDemo()
        await self.server.start("examples.tutorial.ajax.hello_test:hello_test",websockets=False)
        url = self.server.get_url("/")
        await asyncio.sleep(10)
        self.browser.get(url)
        # await asyncio.sleep(self.server.sleep_time)
        divs = self.browser.find_elements(By.TAG_NAME, "div")
        for div in divs:
            div.click()
            await asyncio.sleep(0.1)
        await asyncio.sleep(self.server.sleep_time)
        #debug=self.debug
        debug=True
        for div in divs:
            if debug:
                print(div.text)
            self.assertTrue(f"was clicked 1 times" in div.text)
        self.browser.close()
        await asyncio.sleep(self.server.sleep_time)
        await self.server.stop()