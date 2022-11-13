# Justpy Tutorial demo grid_test9 
# Evaluating Fields using JavaScript       
#      
# generated by write_as_demo  at 2022-11-13T19:18:34.153023+00:00 
# 
# see https://justpy.io/grids_tutorial/field_evaluation#evaluating-fields-using-javascript
import justpy as jp

grid_options = {
    'getDataPath': '''function(data) { return data.orgHierarchy; }''',
    'treeData': True,
    'defaultColDef': {
        'filter': True,
        'sortable': True,
        'resizable': True,
    },
    'columnDefs': [
        {'headerName': "job title", 'field': "jobTitle"},
        {'headerName': "employment type", 'field': "employmentType"},
    ],
    'rowData' : [
        {'orgHierarchy': ['Erica'], 'jobTitle': "CEO", 'employmentType': "Permanent"},
        {'orgHierarchy': ['Erica', 'Malcolm'], 'jobTitle': "VP", 'employmentType': "Permanent"},
        {'orgHierarchy': ['Erica', 'Bob'], 'jobTitle': "SVP", 'employmentType': "Permanent"},
        {'orgHierarchy': ['Erica', 'Bob', 'jo'], 'jobTitle': "eVP", 'employmentType': "Permanent"}
    ]
}

def grid_test9():
    wp = jp.WebPage()
    grid = jp.AgGrid(a=wp, options=grid_options)
    grid.evaluate = ['getDataPath']
    return wp

# initialize the demo
from examples.basedemo import Demo
Demo("grid_test9", grid_test9)
