#encoding:utf8
import tornado.ioloop
import tornado.web
import json
import md5
import tornado.httpclient as httpclient
import datetime
import time
import sys
# sys.path.append("lib")
import base64
import uuid
import urllib
import logging
import logging.config
import redis
import tornado.websocket
import ConfigParser
import getopt
reload(sys)
sys.setdefaultencoding('utf8')

# init logger and load config
logging.config.fileConfig('config/logging.ini')
logger = logging.getLogger('long_gateway.log')
cf = ConfigParser.ConfigParser()
cf.read('config/config.ini')
# connect to redis
r = redis.StrictRedis(cf.get("redis","host"), port=cf.get("redis","port"), db=cf.get("redis","db"),password=cf.get("redis","password"))
# init global
HOST = cf.get("server","host")
PORT = cf.get("server","port")
connected_user   = {}
topics           = {}
last_notify_time = 0



class BaseHandler(tornado.web.RequestHandler):

    def formatReturn(self,code,data=[]):
        rtn = {}
        rtn['code'] = code
        rtn['data'] = data

        self.write(json.dumps(rtn))
        self.finish()

class PushHandler(tornado.web.RequestHandler):


    def empty_response_handler(self):
        pass
    # 用户查找策略
    # 先在本机查找
    # 本机找不到去 中心服查找
    # 缓存路由信息到LRU缓存
    # 都查找不到 说明用户离线
    def push(self,app,userIds,content):
        logger.debug(content)
        user_not_find = []
        for userId in userIds:
            connect_user_key = "%s:%s"%(app,userId)
            if connect_user_key in connected_user:
                connected_user[connect_user_key].write_message(content)
            else:
                user_not_find.append(userId)
        # 批量取出不在本机用户的主机地址
        pipe = r.pipeline()
        for userId in user_not_find:
            pipe.hget(app,userId)
        host_list  = pipe.execute()

        # logger.debug(host_list)
        # if host_list:
        #     logger.debug('user not found and not in info center!')
        host_set      = {}
        self.users_offline = []


        for index,host in enumerate(host_list):
            if not host:
                # 记录下未找到的用户
                self.users_offline.append(user_not_find[index])
                logger.debug("user not alive:%s"%(user_not_find[index]))
                continue
            if host in host_set:
                host_set[host].append(user_not_find[index])
            else:
                host_set[host] = list()
                host_set[host].append(user_not_find[index])
        # 从redis中移除这些不在线的用户
        if "%s:%s"%(HOST,PORT) in host_set:
            for offline_user in host_set["%s:%s"%(HOST,PORT)]:
                # 清理离线用户
                r.hdel(app,offline_user)
            del host_set["%s:%s"%(HOST,PORT)]

        client = tornado.httpclient.AsyncHTTPClient()
        for host in host_set:
            logger.debug("redirect ->%s"%host)
            response = client.fetch("http://%s/push/user?app=%s&userId=%s&content=%s"%(host,app,','.join(host_set[host]),content), method='GET',callback = self.empty_response_handler)







class PushUserHandler(PushHandler):
    # @tornado.web.asynchronous
    def post(self):
        self.get()

    # @tornado.web.asynchronous
    def get(self):
        app      = self.get_argument('app')
        userId   = self.get_argument('userId')
        content  = self.get_argument('content')
        logger.debug("push to app:%s user:%s content:%s"%(app,userId,content))
        self.push(app,userId.split(','),content)
        self.finish()
        # connect_user_key = "%s:%s"%(app,userId)
        # if connect_user_key in connected_user:
        #     connected_user[connect_user_key].write_message(content)

class PushTopicHandler(PushUserHandler):

    @tornado.web.asynchronous
    def post(self):
        self.get()

    @tornado.web.asynchronous
    def get(self):
        app      = self.get_argument('app')
        topic    = self.get_argument('topic')
        content  = self.get_argument('content')
        topic_key = "topic:%s:%s"%(app,topic)
        users_intopic = r.smembers(topic_key)
        # logger.debug(users_intopic)
        self.push(app,users_intopic,content)
        # 移除topic中不在线的用户
        # logger.debug(self.users_offline)
        pipe = r.pipeline()
        for user_offline in self.users_offline:
            pipe.srem(topic_key,user_offline)
        pipe.execute()

        # for offline_user in self.users_offline:
        self.finish()
        # if topic_key in topics:
        #     for userId in topics[topic_key]:
        #         connect_user_key = "%s:%s"%(app,userId)
        #         logger.debug(connect_user_key)
        #         if connect_user_key in connected_user:
        #             connected_user[connect_user_key].write_message(content)
        #         else:
        #             topics[topic_key].remove(e)



class GetServerHandler(BaseHandler):

    def get(self):
        # 从redis获取可用服务器列表
        # 根据用户id选取一台server
        server_list = r.get('server_list')
        if server_list:
            app         = self.get_argument('app',False)
            userId      = self.get_argument('userId',False)
            if not app  or not userId:
                self.formatReturn(1,'param error')

            server_list = json.loads( server_list )
            server_index = self.hash_one("%s:%s"%(app,userId),server_list)
            self.formatReturn(0,server_list[server_index])
        else:
            self.formatReturn(2,'no server avaliable')
            logger.error('no server avaliable!please checke redis.')

    def hash_one(self,userKey,server_list):
        return 0

class ConnectionHandler(tornado.websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        # print("WebSocket opened")
        logger.debug('on open')
        self.lastUserId = False
        pass

    def on_message(self, message):
        logger.debug("Message--->:%s"%message)
        rec = message.split(':')
        cmd   = rec[0]
        app   = rec[1]
        if cmd == 'reg':
            userId = rec[2]
            # 如果不是第一次连接 需要删除以前的链接信息
            if self.lastUserId != False:
                del connected_user["%s:%s"%(self.lastApp,self.lastUserId)]
                r.hdel(self.lastApp,self.lastUserId)
            self.connect_user_key = "%s:%s"%(app,userId)
            self.lastUserId = userId
            self.lastApp    = app
            connected_user[self.connect_user_key] = self
            logger.debug("Register: %s"%self.connect_user_key)
            # 把连接信息记录到redis key为用户id value为主机地址
            # logger.debug("%s %s:%s"%(app,HOST,PORT))
            r.hset(app,userId,"%s:%s"%(HOST,PORT) )

        elif cmd == 'in':
            userId = rec[2]
            topic  = rec[3]
            self.topic_key = "topic:%s:%s"%(app,topic)
            r.sadd(self.topic_key,userId)
        elif cmd == 'out':
            userId = rec[2]
            topic  = rec[3]
            self.topic_key = "topic:%s:%s"%(app,topic)
            r.srem(self.topic_key,userId)
        else:
            self.write_message("error msg format")
            # if self.topic_key in topics:
            #     topics[self.topic_key].add(userId)
            # else:
            #     topics[self.topic_key] = set()
            #     topics[self.topic_key].add(userId)

    def write(self,message):
        self.write_message(message)

    def on_close(self):
        logger.debug("Closed---->%s"%self.connect_user_key)
        connect_user_info = self.connect_user_key.split(':')
        del connected_user[self.connect_user_key]
        r.hdel(connect_user_info[0],connect_user_info[1])
        logger.debug("%s %s leaved "% (connect_user_info[0],connect_user_info[1]))


# 获取topic在线列表
class OnlineTopicHandler(BaseHandler):

    def get(self):
        self.post()

    def post(self):
        app      = self.get_argument('app')
        topic    = self.get_argument('topic')
        topic_key = "topic:%s:%s"%(app,topic)
        users_intopic = r.smembers(topic_key)
        self.formatReturn(0,list(users_intopic))







def make_app():
    return tornado.web.Application([
        (r"/serverList", GetServerHandler),
        (r"/push/user", PushUserHandler),
        (r"/push/topic", PushTopicHandler),
        (r"/online/topic", OnlineTopicHandler),
        (r"/connection", ConnectionHandler),
        (r"/(.*\.(htm|html|js|css|woff2|woff|ttf))", tornado.web.StaticFileHandler, {"path": "example"}),
    ],debug=True)

def parse_param():
    opts,args = getopt.getopt(sys.argv[1:],"p:")
    for op,value in opts:
        if op == '-p':
            global PORT
            PORT = value

if __name__ == "__main__":
    parse_param()
    app = make_app()
    app.listen(PORT)
    logger.info('long gatewat server start at port:%s'%PORT)
    tornado.ioloop.IOLoop.current().start()
