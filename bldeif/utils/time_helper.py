import time

class TimeHelper:
    def __init__(self, time_str):
        self.time_str = time_str
        self.epoch = self.getTimestampFromString()

    def getTimestampFromString(self):
        # Bamboo returns datetime in this format: "2017-06-12T13:55:39.712-06:00"
        # remove last colon
        last_colon_idx = self.time_str.rfind(':')
        li = list(self.time_str)
        li.pop(last_colon_idx)
        self.time_str = ''.join(li)

        # convert to epoch
        pattern = '%Y-%m-%dT%H:%M:%S.%f%z'
        epoch = int(time.mktime(time.strptime(self.time_str, pattern)))
        return epoch