import time
import calendar
import re

class TimeHelper:
    def secondsFromString(self, time_str):
        tz_offset_with_colon = re.compile(r'.\d+-\d\d:\d\d$')
        if tz_offset_with_colon.search(time_str):
            time_str = self.popLastColon(time_str)
        struct = self.parseTimeStringToStruct(time_str)
        secs = int(time.mktime(struct))
        return secs

    def secondsFromStruct(self, struct):
        return calendar.timegm(struct)


    def structFromSeconds(self, secs, zone='utc'):
        return {
            'local': time.localtime(secs),
            'utc'  : time.gmtime(secs)
        }[zone]

    def stringFromStruct(self, struct, format):
        return time.strftime(format, struct)

    def stringFromSeconds(self, secs, format, zone='utc'):
        struct = self.structFromSeconds(secs, zone)
        str    = self.stringFromStruct(struct, format)
        return str


    def popLastColon(self, time_str):
        # example of string returned by Bamboo: '2017-06-12T13:55:39.712-06:00'
        # remove last colon
        last_colon_idx = time_str.rfind(':')
        li = list(time_str)
        li.pop(last_colon_idx)
        return  ''.join(li)

    def parseTimeStringToStruct(self, time_str):
        try:
            return time.strptime(time_str, '%Y-%m-%d %H:%M:%S Z')
        except ValueError:
            pass

        try:
            return time.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%f%z')
        except ValueError:
            pass

        try:
            return time.strptime(time_str, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            pass

        try:
            return time.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            pass

        return False

    def getTimeZone(self):
        daylight = time.daylight
        tuple_idx = 0
        if daylight == 1:
            tuple_idx = 1

        return time.tzname[tuple_idx]

    def getOffset(self):
        utc    = time.gmtime()
        local  = time.localtime()
        return local.tm_hour - utc.tm_hour







# import time
# import re
#
# class TimeHelper:
#     def __init__(self, time_str):
#         self.time_str = time_str
#         #self.epoch = self.getTimestampFromString()
#
#     def getTimestampFromString(self):
#         bamboo_time = re.compile(r'.\d+-\d\d:\d\d$')
#         if bamboo_time.search(self.time_str):
#             self.popLastColumn()
#         parsed_time = self.parseTime()
#         epoch = int(time.mktime(parsed_time))
#         return epoch
#
#     def popLastColumn(self):
#         # example of string returned by Bamboo: '2017-06-12T13:55:39.712-06:00'
#         # remove last colon
#         last_colon_idx = self.time_str.rfind(':')
#         li = list(self.time_str)
#         li.pop(last_colon_idx)
#         self.time_str = ''.join(li)
#
#     def parseTime(self):
#         try:
#             return time.strptime(self.time_str, '%Y-%m-%d %H:%M:%S Z')
#         except ValueError:
#             pass
#
#         try:
#             return time.strptime(self.time_str, '%Y-%m-%dT%H:%M:%S.%f%z')
#         except ValueError:
#             pass
#
#         return False


