from multiprocessing import Process
from jpcore.mytest_child import entry_point

if __name__=="__main__":
    proc = Process(
    target=entry_point,
    args=("hi",)
    )
    proc.daemon = True
    proc.start()
    print("started")
    a=input()
    print("killing")
    proc.terminate()