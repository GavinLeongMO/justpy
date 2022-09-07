"""
Created on 2022-09-07

@author: hr
"""
import yaml

from tests.basetest import Basetest
from addict import Dict


class TestJavaScriptObject(Basetest):
    """
    Tests JavaScript object conversion via PyYaml
    """

    def test_decode(self):
        """
        test JavaScript object decoding
        """
        # example options string see
        # https://www.highcharts.com/docs/getting-started/how-to-set-options
        options_string = """{
    chart: {
        renderTo: 'container',
        type: 'bar'
    },
    title: {
        text: 'Fruit Consumption'
    },
    xAxis: {
        categories: ['Apples', 'Bananas', 'Oranges']
    },
    yAxis: {
        title: {
            text: 'Fruit eaten'
        }
    },
    series: [{
        name: 'Jane',
        data: [1, 0, 4]
    }, {
        name: 'John',
        data: [5, 7, 3]
    }]
}"""
        options = Dict(yaml.full_load(options_string.encode("ascii", "ignore")))
        debug = self.debug
        # debug=True
        if debug:
            print(options)
        self.assertTrue("chart" in options)
        pass

    def test_decode_no_separating_spaces(self):
        """
        test JavaScript object decoding
        """
        # example options string see
        # https://www.highcharts.com/docs/getting-started/how-to-set-options
        options_string = """{
    title:{
        text: 'Fruit Consumption'
    },
    xAxis: {
        categories: ['Apples', 'Bananas', 'Oranges']
    },
    series:[]
}"""
        options = Dict(yaml.full_load(options_string.encode("ascii", "ignore")))
        debug = self.debug
        # debug=True
        if debug:
            print(options)
        self.assertTrue("series" in options)
        self.assertTrue("title" in options)
        self.assertTrue("text" in options["title"])
        pass
