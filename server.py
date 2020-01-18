import os
import sys
import socket
import threading
import json
import struct
import time
import hashlib

class Communication(object):
  def __init__(self):
    pass
  def recv_data(self, sock):
    # Read data length and unpack it into an integer
    raw_data = self.recvall(sock, 4)
    if not raw_data:
        return None
    data = struct.unpack('>I', raw_data)[0]
    # Read the data
    return self.recvall(sock, data)

  def recvall(self, sock, n):
    # Helper function to recv n bytes or return None if EOF is hit
    # Since recv is blocking, and we have set the socket to non-blocking,
    # so we use try-except to catch the conflict error and ignore
    try:
      data = bytearray()
      while len(data) < n:
          packet = sock.recv(n - len(data))
          if not packet:
              return None
          data.extend(packet)
      return data
    except:
      pass

  def send_data(self, sock, data):
    # Prefix each message with a 4-byte length (network byte order)
    try:
      data = struct.pack('>I', len(data)) + data
      sock.sendall(data)
      return True
    except:
      return False

  def send_to_all(self, data):
    finished = []
    while len(finished) < len(online_user_list):
      for user, user_sock in online_user_list.items():
        if user not in finished:
          if black_list.get(user) == None or self.sender not in black_list[user]:
            lock.acquire(timeout=1)
            self.send_data(user_sock, data)
            finished.append(user)
            lock.release()
          else:
            # if sender was in receiver's blacklist, don't send msg to receiver
            finished.append(user)

class Daemon_thread(threading.Thread, Communication):
  def __init__(self):
    threading.Thread.__init__(self)

  def run(self):
    data = json.dumps({'type': 'ACK',
                      }).encode()
    while True:
      for user in list(online_user_list.keys()):
        lock.acquire(timeout=1)
        if self.send_data(online_user_list[user], data) == False:
          online_user_list.pop(user)
          print('[system] %s connection was broke.' % user)
        lock.release()   

      time.sleep(1)


class Server_thread(threading.Thread, Communication):
    def __init__(self, client_addr, client_sock):
      threading.Thread.__init__(self)
      self.client_sock = client_sock
      self.client_addr = client_addr
      print ("New connection added: ", client_addr, client_sock)

    #override Communication.send_data()
    def send_data(self, sock, data):
      try:
        data = struct.pack('>I', len(data)) + data
        sock.sendall(data)
      except:
        pass

    def login(self):
      if self.sender in online_user_list:
        data = json.dumps({'login': 'fail',
                           'errormessage': '%s is online' % self.sender,
                          }).encode()
        self.send_data(self.client_sock, data)
      else:
        with open('./data/PasswordTable.json', 'r') as f:
          table = json.load(f)
        username = hashlib.sha1()
        username.update(self.sender.encode("utf-8"))
        password = table.get(username.hexdigest())          
        if password == None:
          data = json.dumps({'login': 'fail',
                             'errormessage': ' username %s does not exist.' % self.sender,
                             }).encode()
          self.send_data(self.client_sock, data)
        else:
          check_password = hashlib.sha1()
          check_password.update(self.password.encode("utf-8"))
          if not check_password.hexdigest() == password:
            data = json.dumps({'login': 'fail',
                               'errormessage': ' password is not correct.',
                              }).encode()
            self.send_data(self.client_sock, data)
          else: 
            # notify other users that a new user join 
            data = json.dumps({'type': 'broadcast',
                               'message': '[system] ' + self.sender + ' has logged in.',
                              }).encode()
            self.send_to_all(data)

            if self.sender not in user_list:
              user_list.append(self.sender)
            online_user_list[self.sender] = self.client_sock
            print(self.sender, self.client_sock, 'login success！')
            data = json.dumps({'login': 'success',
                              }).encode()

            lock.acquire()
            self.send_data(online_user_list[self.sender], data)
            lock.release()

    def store_file(self):
      while(True):
        buffer = self.recv_data(self.client_sock)
        # since client_sock is nonblocking, buffer could be None,
        # but json.loads can't load None value
        if not buffer == None:
          break

      data_dir = os.path.join('./data', self.receiver)
      if not os.path.exists(data_dir):
        os.makedirs(data_dir)
      file_path = os.path.join(data_dir, self.file_name)
      with open(file_path, 'wb') as f:
        f.write(buffer)

      print('%s was saved' % file_path)


    def broadcast(self):
      data = json.dumps({'type': 'broadcast',
                         'message': self.sender + ':' + self.message,
                        }).encode()
      self.send_to_all(data)

    def private_send(self):
      if self.receiver in user_list:
        # check whether receiver is online
        if self.receiver not in online_user_list:
          self.store_msg(False)
        else:
          self.store_msg(True)
          data = json.dumps({'type': 'send',
                             'message': self.sender + ':' + self.message,
                            }).encode()
          self.send_data(online_user_list[self.receiver], data)
      else:
        pass

    def list_users(self):
      offline_user_list = set(user_list) - set(online_user_list.keys())
      users = {'offline': list(offline_user_list), 
               'online': list(online_user_list.keys())}
      
      data = json.dumps({'type': 'list_users',
                         'message': users,
                        }).encode()

      self.send_data(online_user_list[self.sender], data)

    def exit(self):
      online_user_list.pop(self.sender, None)
      # send the exit message to other users
      data = json.dumps({'type': 'broadcast',
                         'message': '[system]' + self.sender + ' was offline.'
                        }).encode()
      self.send_to_all(data)

    def sendfile(self):
      if self.receiver in user_list:
        if self.receiver not in online_user_list:
          data = json.dumps({'type': 'sendfile',
                             'message': self.receiver + ' not exist or not online.please try later.',
                            }).encode()
          self.send_data(online_user_list[self.sender], data)
        else:
          self.store_file()
          data = json.dumps({'type': 'sendfile',
                             'message': self.sender + (" send a file '%s' to you." % self.file_name),
                            }).encode()
          self.send_data(online_user_list[self.receiver], data)
      else:
        pass

    def history(self):
      history_type = 0
      try:
        history_type = int(self.command)
      except:
        print('history_type error!')
        return

      total_len = 0
      read_len = 0
      cnt_path = os.path.join("./msg", self.receiver + '.cnt')
      with open(cnt_path, 'r') as f:
        length = f.read()
        length = length.split(' ')
        total_len = int(length[0])
        read_len  = int(length[1])
        f.close()

      if history_type > total_len:
        history_type = total_len

      if history_type != 0:
        history_path = os.path.join("./msg", self.receiver + '.history')
        with open(history_path, 'r') as f:
          histories = f.read().split('\n')
          for i in range(total_len - history_type, total_len):
            message = histories[i].split(' ')
            SENDER = message[1]
            RECEIVER = message[2]
            msg = " ".join(message[3:])
            data = json.dumps({'type': 'send',
                               'message': SENDER + ':' + msg,
                              }).encode()
            self.send_data(online_user_list[self.receiver], data)
      else:
        history_path = os.path.join("./msg", self.receiver + '.history')
        with open(history_path, 'r') as f:
          histories = f.read().split('\n')
          for i in range(read_len, total_len):
            message = histories[i].split(' ')
            SENDER = message[1]
            RECEIVER = message[2]
            msg = " ".join(message[3:])
            data = json.dumps({'type': 'send', 'message': SENDER + ':' + msg,}).encode()
            self.send_data(online_user_list[self.receiver], data)
        with open(cnt_path, 'w') as f:
          f.write(str(total_len) + ' ' + str(total_len))
          f.close()

    def store_msg(self, flag):
      data_dir = os.path.join('./msg')
      if not os.path.exists(data_dir):
        os.makedirs(data_dir)
      
      #write message history
      history_path = os.path.join(data_dir, self.receiver + '.history')
      with open(history_path, 'a') as f:
        f.write(self.type + ' ' + self.sender + ' ' + self.receiver + ' ' + self.message + '\n')

      #save cnt
      cnt_path = os.path.join(data_dir, self.receiver + '.cnt')
      total_len = 0
      read_len = 0
      try:
        with open(cnt_path, 'r') as f:
          length = f.read()
          length = length.split(' ')
          total_len = int(length[0])
          read_len  = int(length[1])
          f.close()
      except:
        pass
      with open(cnt_path, 'w') as f:
        if flag == True:  
          f.write(str(total_len + 1) + ' ' + str(read_len + 1))
        else:
          f.write(str(total_len + 1) + ' ' + str(read_len))
        f.close()

    def blacklist(self):
      if self.command == 'add':
        if black_list.get(self.sender) == None:
          black_list[self.sender] = [self.receiver]
        else:
          black_list[self.sender].append(self.receiver) 
      elif self.command == 'rm':
        if black_list.get(self.sender) != None and self.receiver in black_list[self.sender]:
          black_list[self.sender].remove(self.receiver) 
    
    def  getfile(self):
      data_dir = os.path.join('./data', self.sender)
      file_path = os.path.join(data_dir, self.file_name)
      if not os.path.exists(file_path):
        data = json.dumps({'type': 'getfile',
                           'result': False,
                           'message': self.file_name + 'was not found in server.',
                          }).encode()
        self.send_data(online_user_list[self.sender], data)
      else:
        data = json.dumps({'type': 'getfile',
                           'result': True,
                           'file_name':self.file_name,
                           'message': self.file_name + 'is sended to you.',
                          }).encode()
        self.send_data(online_user_list[self.sender], data)

        print('%s is now getting file %s...'%(self.sender,self.file_name)) 
        with open(file_path, 'rb') as f:
          file = f.read()
        self.send_data(online_user_list[self.sender], file)    
        print('the file %s is sended to %s.'%(self.file_name,self.sender)) 

    def signup(self):
      with open('./data/PasswordTable.json', 'r') as f:
        table = json.load(f)
      username = hashlib.sha1()
      username.update(self.sender.encode("utf-8"))
      password = table.get(username.hexdigest())
      if password == None:
        print('username %s is available.'%self.sender)
        data = json.dumps({'type':'signup',
                           'signup':'success',
                           'message':'[Server] Signup is successful, your account is added.',
                          }).encode()
        self.send_data(self.client_sock,data)
        password = hashlib.sha1()
        password.update(self.password.encode("utf-8"))
        table[username.hexdigest()] = password.hexdigest()
        with open('./data/PasswordTable.json', 'w') as f:
          json.dump(table,f)
          print('passwordtable is updated.')
      else:
        data = json.dumps({'type':'signup',
                           'signup':'fail',
                           'errormessage':'username has been used, please try other username.',
                          }).encode()
        self.send_data(self.client_sock,data)
    
    def run(self):
      while True:
        buffer = self.recv_data(self.client_sock)
        # since client_sock is nonblocking, buffer could be None,
        # but json.loads can't load None value
        if buffer == None:
          continue
        
        self.js = json.loads(buffer.decode())
        self.type = self.js.get('type')
        self.sender = self.js.get('sender')
        self.receiver = self.js.get('receiver')
        self.message = self.js.get('message')
        self.file_name = self.js.get('file_name')
        self.password = self.js.get('password')
        self.command = self.js.get('command')

        if self.type == 'signup':
          self.signup()

        elif self.type == 'login':
          self.login()
        
        elif self.type == 'broadcast':
          self.broadcast()

        elif self.type == 'send':
          if black_list.get(self.receiver) == None or self.sender not in black_list[self.receiver]:
            self.private_send()

        elif self.type == 'list_users':
          self.list_users()

        elif self.type == 'exit':
          self.exit()

        elif self.type == 'sendfile':
          if black_list.get(self.receiver) == None or self.sender not in black_list[self.receiver]:
            self.sendfile()

        elif self.type == 'getfile':
          self.getfile()

        elif self.type == 'history':
          self.history()

        elif self.type == 'blacklist':
          self.blacklist()



if __name__ == '__main__':
    MAXN = 100
    threads = []
    user_list = []
    online_user_list = {}
    black_list = {}
    if not os.path.exists('./data'):
      os.makedirs('./data')
    if not os.path.exists('./data/PasswordTable.json'):
      with open('./data/PasswordTable.json', 'w') as f:
        json.dump({},f)

    server_addr = "0.0.0.0"
    server_port = 12416
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #set server to be nonblocking
    server.setblocking(False)
    server.bind((server_addr, server_port))
    server.listen(MAXN)
    print("Server started")

    connection_check_thread = Daemon_thread()
    connection_check_thread.setDaemon(True)
    connection_check_thread.start()

    #connection_check = threading.Thread(target=self.connection_check_thread)

    lock = threading.Lock()  

    # Use try-except to avoid s.accept() return error message
    while True:
      try:
        client_sock, client_addr = server.accept()
        thread = Server_thread(client_addr, client_sock)
        thread.setDaemon(True)
        thread.start()
        threads.append(thread)

        '''
        if len(threads) >= MAXN:
          for thread in threads:
            thread.join()
        threads = [] 

        time.sleep(1)
        '''

      except:
        pass