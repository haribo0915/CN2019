import os
import sys
import socket
import threading
import json
from cmd import Cmd
import time
import struct
  
class Client(Cmd):
  prompt = '>>>'
  intro = '[Welcome] simple chatroom client interface\n' + '[Welcome] type help to get hints\n'
  
  def __init__(self, server):    
    super().__init__()
    self.server_addr = server[0]
    self.server_port = server[1]
    self.recv_msg_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   
    self.recv_msg_socket.connect((self.server_addr, self.server_port))
    time.sleep(1)
    self.send_msg_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.send_msg_socket.connect((self.server_addr, self.server_port))

    self.recv_thread = None
    self.recv_thread_alive = False
    self.username = None
    self.password = None

    self.daemon = threading.Thread(target=self.daemon_thread)
    self.daemon.setDaemon(True)
    self.daemon.start()

  def daemon_thread(self):
    while True:
      if type(self.recv_thread) == type(self.daemon):
        self.recv_thread.join()
        self.recv_thread = None
        self.recv_thread_alive = False
        self.reconnect()
        
      time.sleep(1)

  def reconnect(self):
    self.recv_msg_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   
    self.recv_msg_socket.connect((self.server_addr, self.server_port))
    time.sleep(1)
    self.send_msg_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.send_msg_socket.connect((self.server_addr, self.server_port))

    self.re_login()

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
    try:
      data = bytearray()
      while len(data) < n:
          packet = sock.recv(n - len(data))
          if not packet:
              return None
          data.extend(packet)
      return data
    except:
      return None

  def send_data(self, sock, data):
    # Prefix each message with a 4-byte length (network byte order)
    try:
      data = struct.pack('>I', len(data)) + data
      sock.sendall(data)
    except:
      print('[system] send fail !!')

  def re_login(self):
    data = json.dumps({'type': 'login',
                       'sender': self.username,
                       'password': self.password
                      }).encode()

    time.sleep(2)
    self.send_data(self.recv_msg_socket, data)

    buffer = self.recv_data(self.recv_msg_socket)
    js = json.loads(buffer.decode())

    if js['login'] == 'success':
      self.recv_thread_alive = True
      self.recv_thread = threading.Thread(target=self.receive_message_thread)
      self.recv_thread.setDaemon(True)
      self.recv_thread.start()
      print('[Client] success to reconnect')
    else:
      print('[Client] fail to reconnect')

  def receive_message_thread(self):
    while self.recv_thread_alive:
      buffer = self.recv_data(self.recv_msg_socket)
      if buffer == None:
        break
      
      js = json.loads(buffer.decode())
 
      type_ = js['type']
      message = js.get('message')
      types = ['message', 'list_users', 'broadcast', 'send', 'exit', 'sendfile']

      if type_ in types:
        print(message)

      elif type_ == 'ACK':
        pass

      elif type_ == 'getfile':
        if js['result'] == True:
          buffer = self.recv_data(self.recv_msg_socket)
          if buffer == None:
            break

          data_dir = os.path.join('./client_data', self.username)
          if not os.path.exists(data_dir):
            os.makedirs(data_dir)
          file_path = os.path.join(data_dir,js['file_name'])
          with open(file_path, 'wb') as f:
            f.write(buffer)
          print('%s was saved' % file_path)
        else:
          print(message)
  
  def send_broadcast_message_thread(self, message):
    data = json.dumps({'type': 'broadcast',
                       'sender': self.username,
                       'message': message,
                      }).encode()

    lock.acquire()
    self.send_data(self.send_msg_socket, data)
    lock.release()
  
  def send_private_message_thread(self, receiver, message):
    data = json.dumps({'type': 'send',
                       'receiver': receiver,
                       'sender': self.username,
                       'message': message,
                      }).encode()

    lock.acquire()
    self.send_data(self.send_msg_socket, data)
    lock.release()

  def send_file_thread(self, receiver, file_path, file_name):
    print('[system]', 'sending the file...')
    send_file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    send_file_socket.connect((self.server_addr, self.server_port))
    with open(file_path, 'rb') as f:
      file = f.read()
    data = json.dumps({'type': 'sendfile',
                       'sender': self.username,
                       'receiver': receiver,
                       'file_name': file_name,
                      }).encode()   
    self.send_data(send_file_socket, data)
    self.send_data(send_file_socket, file)  
    print('[system]', 'the file is sended.')  
    send_file_socket.close()

  def blacklist_thread(self, receiver, command):
    data = json.dumps({'type': 'blacklist',
                       'receiver': receiver,
                       'sender': self.username,
                       'command': command,
                      }).encode()

    lock.acquire()
    self.send_data(self.send_msg_socket, data)
    lock.release()

  def send_exit(self):
    data = json.dumps({'type': 'exit',
                       'sender': self.username,
                      }).encode()

    lock.acquire()
    self.send_data(self.send_msg_socket, data)
    lock.release()
  
  def start(self):
    self.cmdloop()

  def login(self, username, password):
    data = json.dumps({'type': 'login',
                       'sender': username,
                       'password':password
                      }).encode()
    self.send_data(self.recv_msg_socket, data)

    buffer = self.recv_data(self.recv_msg_socket)


    js = json.loads(buffer.decode())

    if js.get('login') != None:
      if js['login'] == 'success':
        self.username = username
        self.password = password
        # create new thread for receiving message
        self.recv_thread_alive = True
        self.recv_thread = threading.Thread(target=self.receive_message_thread)
        self.recv_thread.setDaemon(True)
        self.recv_thread.start()
        print('[Client] success to login')
      else:
        print('[Client] fail to login, ', js['errormessage'])
  
  def do_login(self, args):
    if not self.username is None:
      print('please exit first!')
      return

    print('please type your username:')
    username = input().split(' ')[0]
    print('please type your password:')
    password = input().split(' ')[0]
  
    self.login(username, password)
  
  def do_send(self, args):
    if self.username is None:
      print('please login first!')
      return

    command = args.split(' ')

    if len(command) == 0:
      print('please check your parameters')
      return

    receiver = command[0]
    message = ' '.join(command[1:])
    # create new thread for sending message
    if receiver == 'all':
      thread = threading.Thread(target=self.send_broadcast_message_thread, args=(message, ))
    else:
      thread = threading.Thread(target=self.send_private_message_thread, args=(receiver, message))
    thread.setDaemon(True)
    thread.start()
  
  def do_list_users(self, args):
    if self.username is None:
      print('please login first!')
      return

    list_message = json.dumps({'type': 'list_users',
                               'sender': self.username,
                              }).encode()
    self.send_data(self.send_msg_socket, list_message)
  
  def do_help(self, args):
    command = args.split(' ')[0]
    if command == '':
      print('[Help] signup')
      print('[Help] login - login to chatroom')
      print("[Help] send who message - if who = 'all', it means broadcast")
      print('[Help] list_users - list both offline and online users')
      print('[Help] sendfile who file_num filepath[1], filepath[2],...')
      print('[Help] getfile file_num filename[1], filename[2],...')
      print('[Help] blacklist [add/rm] username - add or remove user in your blacklist')
      print('[Help] history [# of the latest received messages]')
    else:
      print('[Help] command not found')
  
  def do_exit(self, args): 
    print("Exit")
    self.send_exit()
    try:
      exit(0)
    except Exception as e:
      print(e)
  
  def do_sendfile(self, args):
    if self.username is None:
      print('please login first!')
      return

    command = args.split(' ')
    receiver = command[0]
    file_num = int(command[1])
    for i in range(file_num):
      file_path = command[i+2]
      file_name = file_path.split('/')[-1]
   
      if not os.path.exists(file_path):
        print('%s is not exist.' % file_name)
        return
      thread = threading.Thread(target=self.send_file_thread, args=(receiver, file_path, file_name))
      thread.setDaemon(True)
      thread.start()
  
  def do_getfile(self, args):
    if self.username is None:
      print('please login first!')
      return

    command = args.split(' ')
    file_num = int(command[0])    
    for i in range(file_num):
      file_name = command[i+1]
      data = json.dumps({'type': 'getfile',
                         'sender': self.username,
                         'file_name': file_name,
                        }).encode()
      self.send_data(self.send_msg_socket, data)

  #To simulate connection break
  def do_break(self, args):
    if self.username is None:
      print('please login first!')
      return
    time.sleep(1)
    self.recv_msg_socket.close()
    self.send_msg_socket.close()
    print('Connection broke !!')

  def do_blacklist(self, args):
    if self.username is None:
      print('please login first!')
      return

    command = args.split(' ')
    if len(command) != 2:
      print('please check your parameters')
      return

    cmd = command[0]
    receiver = command[1]

    thread = threading.Thread(target=self.blacklist_thread, args=(receiver, cmd))
    thread.setDaemon(True)
    thread.start()

  def do_history(self, args):
    if self.username is None:
      print('please login first!')
      return
    command = args.split(' ')
    list_message = json.dumps({'type': 'history',
                              'receiver': self.username,
                              'command': command[0],
                              }).encode()
    self.send_data(self.send_msg_socket, list_message)

  # override the Cmd method. 
  # The default Cmd.emptyline() will redo the last nonempty cmd
  def emptyline(self):
    pass

  def do_signup(self, args):
    if not self.username is None:
      print('please exit first!')
      return

    print('please type your username:')
    username = input().split(' ')[0]
    print('please type your password:')
    password = input().split(' ')[0]  
    
    data = json.dumps({'type': 'signup',
                       'sender': username,
                       'password': password
                      }).encode()
    self.send_data(self.recv_msg_socket, data) 

    buffer = self.recv_data(self.recv_msg_socket) 
    js = json.loads(buffer)
    if js['signup'] == 'success':
      print(js['message'])
      self.login(username, password)
    else:
      print('[Client] fail to signup, ', js['errormessage'])        
  
if __name__ == '__main__':
  lock = threading.Lock()
  server_addr = "127.0.0.1"
  server_port = 12416

  client = Client((server_addr, server_port))
  client.start()