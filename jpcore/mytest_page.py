import justpy as jp

def homepage():
    wp=jp.WebPage()
    jp.P(text="Hi", a=wp)
    return wp

