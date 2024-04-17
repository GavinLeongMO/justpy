"""
Created on 2022-08-24

@author: wf
"""
import justpy as jp
from tests.base_server_test import BaseAsynctest
import tempfile

class TestJustpyCore(BaseAsynctest):
    """
    Tests for Justpy Core features
    """
    async def asyncSetUp(
        self,
        port: int = 8123,
        host: str = "127.0.0.1",
        sleep_time=None,
        with_server=True,
        debug=False,
        profile=True,
        mode=None,
    ):
        await super().asyncSetUp(mode="process")

    # async def setUp(self):
    #     await BaseAsynctest.setUp(self, port=8122, debug=True)


    async def testWp(self):
        """'
        test the webpage asynchronously
        """
        #self.wp_to_test
        await self.server.start("tests.test_justpy_core:wp_to_test")
        status, rawhtml = await self.getResponseHtml()
        self.assertEqual(200, status)
        html = rawhtml.decode("utf8")
        debug = True
        if debug:
            print(html)
            tmp=tempfile.NamedTemporaryFile(mode="w+t",delete=True)
            tmp.write(html)
            tmp.close()

async def wp_to_test():
    """
    the example Webpage under test
    """
    wp = jp.WebPage()
    _d = jp.Div(a=wp)
    return wp