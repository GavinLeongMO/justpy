# Justpy Tutorial demo hello_test from docs/tutorial/ajax.md
import justpy as jp

def hello_test():
    wp = jp.WebPage()
    for i in range(10):
        jp.Hello(a=wp)
    return wp

# initialize the demo
from  examples.basedemo import Demo
if __name__=='__main__':
    Demo ("hello_test",hello_test, websockets=True)
