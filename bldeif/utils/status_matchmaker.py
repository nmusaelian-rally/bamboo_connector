class Matchmaker:
    def __init__(self, other):
        self.other = other


    def matchStatus(self, status):
        if self.other == 'Bamboo':
            return {
                'Successful': 'SUCCESS',
                'Failed': 'FAILURE'
            }[status]