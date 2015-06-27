
class ConsoleColor(object):
    def __init__(self):
        self.__seq = 40

    def printn(self, s, num):
        if num is not None:
            s = '\033[' + str(num) + 'm' + s + '\033[0m'

        return s

    def print(self, s, clr):
        if clr == 'switch':
            self.__seq = 40 if self.__seq == 100 else 100
            n = self.__seq
        else:
            n = {
                'white': None,
                'red': 91,
                'green': 92,
                'yellow': 93,
                'blue': 94,
                'purple': 95,
                'cyan': 96
            }[clr]

        return self.printn(s, n)


color = ConsoleColor()


def divider(s):
    print('\n--- '+s+' '+''.join(['-' for d in range(80 - len(s) - 5)])+'\n')