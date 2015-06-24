from contextlib import contextmanager

import pymysql


CONFIG_FILENAME = '/etc/glacia.conf'

# Read config file
import configparser
config = configparser.RawConfigParser()
config.read(CONFIG_FILENAME)


@contextmanager
def close_after(ret):
    try:
        yield ret
    finally:
        ret.close()


class Database(object):
    def __init__(self):
        self.__conn = None

    def conn(self):
        if self.__conn is None:
            def rq(s):
                if s.startswith('"') and s.endswith('"'):
                    s = s[1:-1]
                return s

            self.__conn = pymysql.connect(host=rq(config.get('db', 'host')),
                                          port=int(config.get('db', 'port')),
                                          user=rq(config.get('db', 'user')),
                                          passwd=rq(config.get('db', 'passwd')),
                                          db=rq(config.get('db', 'db')))

        return self.__conn

    def close(self):
        if self.__conn is not None:
            self.__conn.close()

    def cur(self):
        return close_after(self.conn().cursor(pymysql.cursors.DictCursor))

    def cmd(self, sql, *params):
        with self.cur() as cur:
            return cur.execute(sql, params).rowcount

    def res(self, sql, *params):
        with self.cur() as cursor:
            cursor.execute(sql, params)
            for row in cursor:
                yield row


def dbconn():
    return close_after(Database())


with dbconn() as db:
    for row in db.res("select 'hi' as `greeting`;"):
        print(row)