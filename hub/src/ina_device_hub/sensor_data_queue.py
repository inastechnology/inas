from queue import Queue
from threading import Lock


# @note センサーからMQTTでSubscribeしたデータを処理部に渡すためのキューを作成します。
# このキューは以下の特徴を持ちます。
# ・データの取り出しはFIFOで行われる
# ・データの取り出しはスレッドセーフである
# ・データの取り出しはブロッキングされる
#
# このキューは以下のように使用します。
#
# ```python
# from ina_device_hub.sensor_data_queue import SensorDataQueue
#
# queue = SensorDataQueue()
#
# queue.put("data1")
# queue.put("data2")
#
# print(queue.get())  # data1
# print(queue.get())  # data2
# ```
# このキューは以下のようにスレッドセーフであることを確認できます。
#
# ```python
# import threading
#
# from ina_device_hub.sensor_data_queue import SensorDataQueue
#
# queue = SensorDataQueue()
#
# def put_data():
#     queue.put("data1")
#     queue.put("data2")
#
# def get_data():
#     print(queue.get())
#     print(queue.get())
#
# t1 = threading.Thread(target=put_data)
# t2 = threading.Thread(target=get_data)
#
# t1.start()
# t2.start()
#
# t1.join()
# t2.join()
# ```
class SensorDataQueue:
    def __init__(self):
        self.queue = Queue()
        self.lock = Lock()

    def put(self, data):
        with self.lock:
            self.queue.put(data)

    def get(self, timeout=None):
        return self.queue.get(timeout=timeout)

    def empty(self):
        return self.queue.empty()

    def task_done(self):
        return self.queue.task_done()


sensor_data_queue = SensorDataQueue()
