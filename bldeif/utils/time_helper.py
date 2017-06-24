import time
import re

class TimeHelper:
    def __init__(self, time_str):
        self.time_str = time_str
        #self.epoch = self.getTimestampFromString()

    def getTimestampFromString(self):
        bamboo_time = re.compile(r'.\d+-\d\d:\d\d$')
        if bamboo_time.search(self.time_str):
            self.popLastColumn()
        parsed_time = self.parseTime()
        epoch = int(time.mktime(parsed_time))
        return epoch

    def popLastColumn(self):
        # example of string returned by Bamboo: '2017-06-12T13:55:39.712-06:00'
        # remove last colon
        last_colon_idx = self.time_str.rfind(':')
        li = list(self.time_str)
        li.pop(last_colon_idx)
        self.time_str = ''.join(li)

    def parseTime(self):
        try:
            return time.strptime(self.time_str, '%Y-%m-%d %H:%M:%S Z')
        except ValueError:
            pass

        try:
            return time.strptime(self.time_str, '%Y-%m-%dT%H:%M:%S.%f%z')
        except ValueError:
            pass

        return False


