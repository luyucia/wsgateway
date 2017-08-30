# wsgateway
websocket gateway
用来方便的实现基于websocket的实时推送.可用于IM系统的开发,实时数据展现,web互动游戏等应用场景.


# 依赖
python 2.7
torando
redis

# 安装说明
- 安装python(参见python官方文档)
- 安装redis server(参见redis官方文档)
- 安装python的tornado模块: pip install tornado
- 安装python的redis模块:pip install redis

# 配置
修改config/config.ini
配置redis的主机地址,用户名密码等

注意:server中的host主要用于部署多台wsgateway时使用,要是一个所有主机都能访问到的地址.

# 运行
```
python wsgateway.py
```
后台运行
```
nohup python wsgateway.py &
```


# 使用
## 概念:
- topic:为主题,用户可以订阅一个主题,服务端可以向该topic发送消息,这样在这个topic中的所有用户均会收到消息
- app:app用来区分不同的应用,可自己定义

## 步骤
- 前端建立websocket连接:例如ws://127.0.0.1:9457/connection
- 发送注册命令格式为reg:appid:userid
- (可选)发送进入topic命令格式为:in:appid:userid:topic
- 推送消息给用户例如:http://127.0.0.1/push/user?app=test&userId=1&content=pullmsg
- (可选)推送消息给一个topic,例如:http://127.0.0.1/push/topic?app=test&topic=room1&content=pullmsg

### 前端
```
var websocket = {
    ws:null,
    appId:false,
    userId:false,
    isConnected:false,
  init:function(appId,userId){
    this.ws          = new WebSocket("ws://127.0.0.1:9457/connection");
    this.appId       = appId;
    this.userId      = userId;
    this.isConnected = false;

    this.ws.onopen = function() {
      // 连接通知服务器,报告自己的id
      var clientId = "id"+Math.round(Math.random()*100000000);
      this.ws.send('reg:'+this.appId+":"+this.userId);
      this.isConnected = true;
      console.log('web_socket open')
    }.bind(this);

    this.ws.onmessage = function (evt) {
        this.isConnected = true;
        //接收到的数据
        console.log(evt.data)
    }.bind(this);
    this.ws.onclose = function(){
      //断线重连
      console.log('connect closed reconnect...')
      websocket.init(this.appId,this.userId)
    }.bind(this)
  },
  inTopic:function(topic){
    console.log('call inTopic')
    this.ws.send('in:'+this.appId+":"+this.userId+":"+topic);
  }
}

var clientId = "id"+Math.round(Math.random()*100000000);
websocket.init('test',clientId)
```
### 后端接口

#### 推送给某用户
- /push/user
- 参数

参数 | 含义
---|---
app | 应用id
userId | 用户id
content|推送内容

例如:
```
http://127.0.0.1/push/user?app=test&userId=1&content=pullmsg
```

#### 推送给某topic
- /push/topic
- 参数

参数 | 含义
---|---
app | 应用id
topic | 主题
content|推送内容

例如:
```
http://127.0.0.1/push/topic?app=test&topic=room1&content=pullmsg
```

